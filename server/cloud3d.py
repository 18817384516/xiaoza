"""Dedicated Meshy geometry generation, with local validation and retained source.

API contract: https://docs.meshy.ai/en/api/{text-to-3d,image-to-3d}
Never reuse the user's language-model key for this separate paid service.
Creation requests are deliberately not retried automatically: a lost response
can still have created a chargeable task. Polls resume from saved task IDs.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import time
from urllib.parse import urlparse

import httpx
import numpy as np
import trimesh

from .modeling import ModelingError, number
from .blender_policy import ScriptPolicyError

ROOT = Path(__file__).resolve().parent.parent
API = 'https://api.meshy.ai/openapi'


def folder_for(identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
        raise ModelingError('找不到专业生成记录。', code='cloud3d_missing')
    return ROOT / '.runtime' / 'cloud3d' / identifier


def retry_request(identifier):
    try:
        return json.loads((folder_for(identifier) / 'request.json').read_text('utf-8'))
    except (OSError, ValueError):
        raise ModelingError('找不到完整的专业生成记录，请重新选择描述与参考图。', code='cloud3d_missing') from None


def save_checkpoint(folder, state):
    temporary = folder / 'checkpoint.tmp'
    temporary.write_text(json.dumps(state, ensure_ascii=False), 'utf-8')
    temporary.replace(folder / 'checkpoint.json')


def api_request(client, method, path, payload=None):
    try:
        response = client.request(method, API + path, json=payload)
    except httpx.RequestError:
        if method == 'POST':
            raise ModelingError('创建请求的连接中断，服务可能已经创建任务。为避免重复扣费，未自动重发；请先在 Meshy 控制台确认任务。', code='cloud3d_create_uncertain') from None
        raise ModelingError('专业3D服务连接中断。已保存任务编号，点击「继续查询」即可恢复，不会重新付费创建。', code='cloud3d_connection') from None
    if response.status_code in (401, 403):
        raise ModelingError('Meshy 拒绝了密钥或模型权限，请在设置中检查独立的 Meshy API 密钥。', code='cloud3d_auth')
    if response.status_code in (402, 429):
        raise ModelingError('Meshy 额度不足或请求过多，请检查该服务账户。', code='cloud3d_quota')
    if not response.is_success:
        raise ModelingError(f'专业3D服务返回 {response.status_code}。请检查账户权限；已创建的任务可继续查询。', code='cloud3d_response')
    try:
        return response.json()
    except ValueError:
        code = 'cloud3d_create_uncertain' if method == 'POST' else 'cloud3d_connection'
        raise ModelingError('服务回复无法读取。请先确认已创建的任务，避免重复创建。', code=code) from None


def wait_task(client, endpoint, task_id, update, cancelled, low, high):
    started = time.monotonic()
    while time.monotonic() - started < 2400:
        if cancelled():
            return None
        task = api_request(client, 'GET', endpoint + '/' + task_id)
        state = task.get('status')
        if state == 'SUCCEEDED':
            return task
        if state in ('FAILED', 'CANCELED', 'CANCELLED', 'EXPIRED'):
            raise ModelingError('专业3D服务未完成本次生成。任务编号已保留，可在该服务控制台查看原因。', code='cloud3d_failed')
        progress = max(0, min(100, float(task.get('progress') or 0)))
        update(progress=round(low + (high-low)*progress/100), stage='专用3D模型正在生成形象' if low < 50 else '正在生成彩色材质', elapsed_seconds=round(time.monotonic()-started))
        for _ in range(15):
            if cancelled():
                return None
            time.sleep(.2)
    raise ModelingError('专业3D服务仍未完成。任务已保留，可点击「继续查询」，不会重新创建。', code='cloud3d_connection')


def download_asset(client, url, destination, cancelled):
    parsed = urlparse(url or '')
    if parsed.scheme != 'https' or parsed.hostname not in ('assets.meshy.ai', 'api.meshy.ai') or parsed.username or parsed.password:
        raise ModelingError('服务返回了未支持的模型下载地址，已停止下载。', code='cloud3d_asset')
    # Do not forward the API Authorization header to a file host or redirects.
    try:
        with httpx.stream('GET', url, timeout=90, follow_redirects=False) as response:
            if not response.is_success:
                raise ModelingError('模型文件下载未完成，点击「继续查询」重新取得下载地址。', code='cloud3d_connection')
            count = 0
            with destination.with_suffix('.partial').open('wb') as file:
                for chunk in response.iter_bytes(262144):
                    if cancelled():
                        return False
                    count += len(chunk)
                    if count > 100_000_000:
                        raise ModelingError('模型文件超过本机100 MB限制，请在服务中降低复杂度。', code='cloud3d_asset')
                    file.write(chunk)
        destination.with_suffix('.partial').replace(destination)
        return True
    except httpx.RequestError:
        raise ModelingError('模型文件下载中断，任务已保留，可继续查询。', code='cloud3d_connection') from None


def validate_glb(path):
    """Only self-contained GLB; no importer may fetch arbitrary URI references."""
    raw = path.read_bytes()
    try:
        magic, version, length = struct.unpack_from('<4sII', raw)
        if magic != b'glTF' or version != 2 or length != len(raw) or length > 100_000_000:
            raise ValueError()
        chunk_size, chunk_type = struct.unpack_from('<II', raw, 12)
        if chunk_type != 0x4e4f534a or chunk_size > 8_000_000:
            raise ValueError()
        document = json.loads(raw[20:20+chunk_size])
        for item in document.get('buffers', []) + document.get('images', []):
            uri = item.get('uri')
            if uri and not uri.startswith('data:'):
                raise ValueError()
        if len(document.get('nodes', [])) > 3000:
            raise ValueError()
    except (ValueError, KeyError, TypeError, struct.error):
        raise ModelingError('生成的GLB格式无效或引用了外部文件，未在本机加载。', code='cloud3d_asset') from None


def prepare_asset(path, height, folder, cancelled):
    """Preserve every source piece; mark unprintable geometry without discarding it."""
    from .blender_bridge import collect_mesh
    validate_glb(path)
    scene = trimesh.load(path, file_type='glb', force='scene', process=False)
    meshes = [part for part in scene.dump() if isinstance(part, trimesh.Trimesh) and len(part.faces)]
    if not meshes or sum(len(part.faces) for part in meshes) > 500_000:
        raise ModelingError('生成模型为空或超过本机50万三角面的处理限制；原始文件已留在任务目录。', code='cloud3d_asset')
    mesh = trimesh.util.concatenate(meshes)
    if not np.isfinite(mesh.vertices).all():
        raise ModelingError('生成模型含有无效坐标。', code='cloud3d_asset')
    # glTF is Y-up; the printable workbench and all exports use Z-up millimeters.
    transform = trimesh.transformations.rotation_matrix(np.pi/2, [1,0,0])
    mesh.apply_transform(transform)
    if mesh.extents[2] < 1e-8:
        raise ModelingError('生成模型没有有效高度。', code='cloud3d_asset')
    mesh.apply_scale(height / mesh.extents[2])
    mesh.apply_translation([-mesh.bounds[:,0].mean(), -mesh.bounds[:,1].mean(), -mesh.bounds[0,2]])
    source = folder / 'mesh.json'
    source.write_text(json.dumps({'vertices': mesh.vertices.tolist(), 'faces': mesh.faces.tolist()}), 'utf-8')
    if cancelled():
        return None
    try:
        printed, stats = collect_mesh(source)
        stats['print_ready'] = True
        return printed, stats
    except ScriptPolicyError as error:
        # A game asset can contain separate clothing, hair and zero-thickness
        # surfaces. Keep the asset and preview instead of deleting detail or
        # telling the user to abandon the description.
        mesh.merge_vertices()
        stats = {'dimensions': [round(float(x),2) for x in mesh.extents], 'volume_cm3': 0,
                 'triangles': len(mesh.faces), 'watertight': bool(mesh.is_watertight),
                 'components': len(mesh.split(only_watertight=False)), 'units': 'mm', 'print_ready': False,
                 'warnings': ['形象已生成并保留全部部件，但未通过打印实体检查；可下载原始GLB进入Blender修复。', str(error)]}
        return mesh, stats


def generate(body, job_id, config, update, cancelled):
    previous = body.previous or {}
    folder = folder_for(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'request.json').write_text(json.dumps(body.model_dump(exclude={'resume_job'}), ensure_ascii=False), 'utf-8')
    # Size edits and project import are local and never start a paid task.
    reusable = previous.get('kind') == 'meshy' and body.prompt == previous.get('prompt') and not body.regenerate and not body.resume_job
    if reusable:
        identifier = previous.get('source_job')
        source = ROOT / 'data' / 'models' / str(identifier) / 'original.glb' if re.fullmatch('[a-f0-9]{32}', str(identifier)) else None
        if source is None or not source.is_file():
            raise ModelingError('找不到原始GLB。JSON只保存作品信息，请在原电脑保留GLB文件。未调用付费服务。', code='cloud3d_missing')
    else:
        if not config.get('meshy_api_key'):
            raise ModelingError('专业形象生成需要单独配置 Meshy API 密钥。', code='cloud3d_not_configured')
        state = {}
        if body.resume_job:
            old = folder_for(body.resume_job)
            try:
                state = json.loads((old / 'checkpoint.json').read_text('utf-8'))
            except (OSError, ValueError):
                raise ModelingError('没有已确认的任务编号。请先在Meshy控制台确认，避免重复付费。', code='cloud3d_create_uncertain') from None
        reference = body.reference
        if not reference and body.sketch:
            from .blender_bridge import sketch_content
            reference = sketch_content(body)[1]['image_url']['url']
        endpoint = state.get('endpoint') or ('/v1/image-to-3d' if reference else '/v2/text-to-3d')
        if endpoint not in ('/v1/image-to-3d', '/v2/text-to-3d'):
            raise ModelingError('任务记录格式错误。', code='cloud3d_missing')
        with httpx.Client(headers={'Authorization': 'Bearer ' + config['meshy_api_key']}, timeout=45) as client:
            if not state.get('task_id'):
                if state.get('creating'):
                    raise ModelingError('上次创建任务的结果不确定，未自动创建第二个任务。请在Meshy控制台确认。', code='cloud3d_create_uncertain')
                if not reference and len(body.prompt) > 800:
                    raise ModelingError('专业形象生成的文字描述请控制在800字以内。', code='cloud3d_input')
                payload = {'ai_model': 'meshy-7.1', 'geometry_resolution': '4k' if body.detail == 'fine' else 'standard',
                           'should_remesh': True, 'target_polycount': 200000 if body.detail == 'fine' else 50000,
                           'target_formats': ['glb']}
                texture = bool(config.get('meshy_texture', True))
                if reference:
                    payload.update(image_url=reference, should_texture=texture, enable_pbr=texture)
                else:
                    payload.update(mode='preview', prompt=body.prompt)
                state = {'endpoint': endpoint, 'creating': True, 'texture': texture}
                save_checkpoint(folder, state)
                if cancelled():
                    return None
                created = api_request(client, 'POST', endpoint, payload)
                task_id = created.get('result')
                if not isinstance(task_id, str) or not re.fullmatch('[A-Za-z0-9-]{1,80}', task_id):
                    raise ModelingError('服务没有返回有效任务编号，请先在控制台确认是否已扣费创建。', code='cloud3d_create_uncertain')
                state.update(task_id=task_id, creating=False)
                save_checkpoint(folder, state)
            else:
                save_checkpoint(folder, state)
            # POST above is never repeated on a resumed task.
            task = wait_task(client, endpoint, state['task_id'], update, cancelled, 12, 68)
            if task is None:
                return None
            if endpoint == '/v2/text-to-3d' and state.get('texture'):
                if not state.get('refine_id'):
                    if state.get('refine_creating'):
                        raise ModelingError('材质任务创建结果不确定，请先在Meshy控制台确认，未重复创建。', code='cloud3d_create_uncertain')
                    state['refine_creating'] = True
                    save_checkpoint(folder, state)
                    if cancelled():
                        return None
                    refined = api_request(client, 'POST', endpoint, {'mode': 'refine', 'preview_task_id': state['task_id'], 'enable_pbr': True, 'target_formats': ['glb']})
                    refine_id = refined.get('result')
                    if not isinstance(refine_id, str) or not re.fullmatch('[A-Za-z0-9-]{1,80}', refine_id):
                        raise ModelingError('材质任务未返回编号，请在服务控制台确认。', code='cloud3d_create_uncertain')
                    state.update(refine_id=refine_id, refine_creating=False)
                    save_checkpoint(folder, state)
                task = wait_task(client, endpoint, state['refine_id'], update, cancelled, 68, 86)
                if task is None:
                    return None
            source = folder / 'original.glb'
            update(progress=88, stage='正在下载原始几何与材质')
            if not download_asset(client, (task.get('model_urls') or {}).get('glb'), source, cancelled):
                return None
    if cancelled():
        return None
    update(progress=91, stage='本地正在核对网格，保留原始形象')
    desired = body.params.get('height') if reusable else number(body.prompt, ['总高','整体高度','高度','高','height'])
    height = float(desired or 120)
    if not 5 <= height <= 250:
        raise ModelingError('专业形象目标高度需要在5–250毫米之间。', code='cloud3d_input')
    result = prepare_asset(source, height, folder, cancelled)
    if result is None:
        return None
    mesh, stats = result
    stats['warnings'].append('彩色GLB中的材质、法线贴图和光照效果不属于可打印几何；单张参考图未显示的背面由模型推测。')
    recipe = {**previous, 'kind': 'meshy', 'category': 'figurine', 'name': previous.get('name', '专业形象创作'),
              'prompt': body.prompt, 'params': {'height': height}, 'source_job': job_id,
              'generator': 'Meshy 7.1 + local mesh validation', 'detail': body.detail,
              'summary': '专用3D模型生成的形象；原始GLB保留全部几何与材质。修改文字会重新创造，不能保证姿态和结构保持不变。'}
    if body.reference:
        recipe['reference'] = body.reference
    if body.sketch:
        recipe['sketch'] = body.sketch
    return recipe, mesh, stats, source
