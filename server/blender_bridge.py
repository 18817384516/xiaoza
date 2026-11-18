"""Language model writes a modeling program; local Blender executes and revises it."""
from __future__ import annotations

import io
import json
import logging
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx
import manifold3d as manifold
import numpy as np
from PIL import Image, ImageDraw
import trimesh

from .blender_policy import ScriptPolicyError, validate_script
from .modeling import ModelingError, number
from .model_views import model_views

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("xiaozao.blender")
SYSTEM_PROMPT = '''You are an expert Blender 4.5 technical artist and product modeler.
Create a NEW specific 3D model from the user's idea, rather than selecting a template.
Respond with ONE JSON object: {"name":"short Chinese name", "summary":"short Chinese explanation", "code":"complete Python program"}.
The code MUST define create_model() returning a list of Blender objects which form one connected printable solid. Helpers are allowed. Code outside the function may define helpers/constants/imports but must not call create_model itself.
Use Blender's full modeling concepts: custom meshes from vertices/faces, bmesh, curves with bevel, metaballs, booleans, bevel and subdivision modifiers, voxel remesh for organic blends, parametric surfaces with math, etc. You are NOT limited to primitives. Capture the distinctive silhouette, proportions and requested features. Model all important parts, intentional holes and stable flat contacts. Never fake a requested mechanism with decorative geometry; if uncertain mention simplifications in summary.
Coordinates and dimensions are MILLIMETERS, Z up, front -Y. Do not scale by 0.001. Honor all user dimensions; if absent choose a practical 50–100 mm size. Never stretch an exact mechanical part to an arbitrary total height. All positive parts must overlap or connect. Return a stable single part. An optional minimal integrated foot/base is useful, but do not put unrelated large rectangular blocks around the model.
Maintain holes, slots and cavities as real open voids. Single connected material can have cavities. For booleans use modifier.solver='EXACT', set context.view_layer.objects.active and object selection, apply modifier before deleting cutter. Prefer enough overlap (0.5mm). Apply scale before bevel and booleans. Use 32–48 circular segments, subdivision level at most 2, fewer than 250000 vertices / 500000 triangles. Avoid expensive full meshes at tiny voxel sizes. Recalculate face normals on custom meshes. Bevel and smooth appropriate edges, but preserve flat mechanical surfaces. Do not use textures as a substitute for geometry.
Allowed imports ONLY: import bpy, import bmesh, import math, import mathutils, import random; public from math/mathutils imports are allowed. No import aliases. No filesystem, network, external tools, images, libraries, scripts, drivers, handlers, preferences, application state, rendering, save/export, exec/eval/compile/open/getattr/setattr/globals/locals/type, dunder attributes, strings containing double underscores, classes, while loops, with statements or decorators. No bpy.app, bpy.path, bpy.utils, bpy.types, bpy.data.texts or .libraries. No object.id_data or .bl_rna. Avoid material_slots and keyword names filepath/directory. The host saves .blend and exports the returned objects. Never call bpy.ops.wm or import/export operators. Only these bpy.ops categories/operators are available:
object: select_all,delete,join,convert,transform_apply,modifier_apply,shade_smooth,shade_flat,mode_set,origin_set,duplicate,parent_set;
mesh: primitive_cube_add,primitive_uv_sphere_add,primitive_ico_sphere_add,primitive_cylinder_add,primitive_cone_add,primitive_torus_add,primitive_plane_add,primitive_circle_add,select_all,remove_doubles,merge_by_distance,normals_make_consistent,subdivide,extrude_region_move,extrude_faces_move,bevel,delete,fill,edge_face_add;
curve: primitive_bezier_curve_add,primitive_bezier_circle_add,primitive_nurbs_curve_add; transform: translate,rotate,resize.
Other modeling operations should use data APIs/bmesh. Do NOT alias bpy.ops. ShaderNodeScript and external file nodes are forbidden. Do not rely on a window, UI area, display, addons, render engine or user preferences.
Materials optional: use obj.data.materials.append(material). Use simple diffuse_color only; no need to manipulate shader inputs. Avoid legacy mesh.use_auto_smooth. Use bpy.ops.object.convert(target='MESH') for curves if needed. Use mathutils.Vector for vector arithmetic. Use list/tuple numerical coordinates. create_model must always return the final object(s), no cutters, cameras or lights.
If provided a previous program and a requested change, PRESERVE the previous design and edit the program to implement that specific change. Return the complete updated program. If supplied a failure report, fix its cause, preserve the user's design and return complete corrected JSON. Never claim the program was tested; the local host will test it.'''

FINE_PROMPT = '''QUALITY: FINE, finished small sculpture or usable designed product, not a primitive blockout.
Before writing code, decide the distinctive silhouette, proportions, pose and the 4–8 most important requested geometric features. Implement those features deliberately. Put a short Chinese list of implemented features and any omitted requested feature in summary. More polygons alone are NOT more detail.
For characters/animals: shape continuous custom surfaces or deformed meshes with varying cross sections, taper and anatomical transitions. Resolve cheek/muzzle/chin, eyelid rims and eye sockets, inner ears, paws with toe separation, expression and relevant asymmetry. Only add hair, folds, panels, ornaments, seams or fur when appropriate to this particular design; do not cover everything in generic noise or torus rings. Use carefully sampled curves and custom mesh sweeps for sculpted ridges and ornamental lines that follow the actual surface. Keep their roots embedded, not floating. A tube ball assembly is only a construction intermediate.
Separate primary form, secondary forms, and small details in the code. Blend only the PRIMARY organic volumes (at 65mm scale try voxel 0.3–0.45mm, based on bounds and resource limits), then carve sockets/grooves and add relief details AFTER the blend so details survive. Do not re-voxelize the completed sculpture at a coarse resolution. Apply transforms before cuts. Fine raised strokes need meaningful printable thickness (typically 0.65–1mm at 65–80mm scale); keep fine texture shallow and attached. Preserve flat contacts with a properly capped plane cut, never collapse whole layers of vertices to zero height. Keep total below 250000 vertices and 500000 triangles, 2GB memory and 150 seconds. Spend budget on specific features, not uniform subdivisions. 48–64 segments for visible circles, fewer for tiny strokes; subdivision at most 2. Do not make dozens of heavy sequential booleans on a dense mesh: batch/join compatible cutters or attachments.
Reliable union strategy: the host performs an exact Manifold union of the returned closed meshes. You may return the carved body PLUS closed overlapping relief objects (up to 200 total), without expensive sequential Blender UNIONs or a final detail-destroying remesh. Every relief must intersect its supporting solid with a real volume. Convert curves to closed meshes with fill caps. Blender DIFFERENCE cutters must be manifold; joining intersecting cutter shells does not perform a union and can destroy the entire body. Use separate reliable cuts or union the cutters properly. Never delete detached requested features to pass the single-component test; reposition/embed them.
For functional parts: detail means accurate specified holes/slots/countersinks, deliberate edge radii, rib placement and wall transitions, not decoration. Preserve all exact dimensions and interfaces; never invent unspecified mechanisms, ornamental relief, tiny threads or random holes. Leave unrequested interfaces simple. Include only useful support ribs/fillets that do not obstruct fit. State any unimplemented precision feature. Preserve flat mating faces.
For refinements: keep the existing subject, pose, base and requested dimensions; improve its specific forms and details. Do not replace it with a different design. Never imply textures/colors in the .blend are printable geometry.'''

DRAFT_PROMPT = '''QUALITY: QUICK draft of the requested design. Prioritize recognizable silhouette and important functional geometry. Use moderate mesh resolution; organic blending can use 0.5–0.8mm voxels at 65mm scale. Preserve holes and dimensions. Explain simplifications in Chinese summary.'''


def find_blender():
    override = os.getenv("XIAOZAO_BLENDER_PATH", "")
    candidates = [Path(override)] if override else []
    discovered = shutil.which("blender")
    if discovered:
        candidates.append(Path(discovered))
    candidates += sorted((ROOT / "third_party").glob("blender-*/blender.exe"), reverse=True)
    standard = Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Blender Foundation"
    if standard.exists():
        candidates += sorted(standard.glob("Blender */blender.exe"), reverse=True)
    return next((path.resolve() for path in candidates if path.is_file()), None)


def status(config):
    executable = find_blender()
    return {"ready": bool(executable), "installed": bool(executable), "configured": bool(config.get("enabled") and config.get("model") and (config.get("api_key") or urlparse(config.get("base_url", "")).hostname in ("localhost", "127.0.0.1", "::1"))),
            "name": "大模型 + 本地 Blender", "local_modeling": True,
            "service": urlparse(config.get("base_url", "")).hostname, "model": config.get("model", "")}


def endpoints(base):
    base = base.rstrip("/")
    if urlparse(base).path in ("", "/"):
        return [base + "/v1/chat/completions", base + "/chat/completions"]
    return [base + "/chat/completions"]


def sketch_content(body):
    reference = getattr(body, 'reference', None)
    if not body.sketch and not reference:
        return body.prompt
    content = [{"type": "text", "text": body.prompt + "\nUse the attached reference image/sketch to guide silhouette, proportions and specific physical details. Preserve distinctive facial features, clothing layers and accessories. Distinguish geometric relief from color or lighting. The unseen back is an inference; do not claim exact reconstruction."}]
    if reference:
        content.append({"type": "image_url", "image_url": {"url": reference}})
    if not body.sketch:
        return content
    image = Image.new("RGB", (640, 420), "white")
    draw = ImageDraw.Draw(image)
    for path in body.sketch:
        points = [(float(point[0]), float(point[1])) for point in path]
        if len(points) >= 2:
            draw.line(points + [points[0]], fill="#333333", width=4, joint="curve")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    import base64
    content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()}})
    return content


def read_program_response(response, cancelled):
    if "text/event-stream" not in response.headers.get("content-type", "").lower():
        response.read()
        return response.json()["choices"][0]["message"]["content"]
    fragments = []
    complete = False
    size = 0
    for line in response.iter_lines():
        if cancelled():
            return None
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            complete = True
            break
        if not payload:
            continue
        event = json.loads(payload)
        if event.get("error"):
            raise httpx.RemoteProtocolError("Provider interrupted the response")
        for choice in event.get("choices", []):
            text = choice.get("delta", {}).get("content")
            if isinstance(text, str):
                size += len(text)
                if size > 180_000:
                    raise ScriptPolicyError("大模型输出过长，请简化建模步骤。")
                fragments.append(text)
            finish = choice.get("finish_reason")
            if finish == "stop":
                complete = True
            elif finish:
                raise ScriptPolicyError("大模型未完整输出建模步骤，请简化程序并返回完整 JSON。")
    if not complete:
        raise httpx.RemoteProtocolError("Provider closed the stream before completion")
    return "".join(fragments)


def wait_for_retry(cancelled, delay):
    deadline = time.monotonic() + delay
    while time.monotonic() < deadline:
        if cancelled():
            return False
        time.sleep(min(.1, max(0, deadline - time.monotonic())))
    return not cancelled()


def request_program(config, messages, cancelled, update=None):
    if cancelled():
        return None
    errors = []
    urls = endpoints(config["base_url"])
    for url in urls:
        for connection_attempt in range(3):
            if cancelled():
                return None
            try:
                # The request runs in a cancellable daemon thread in generate(); secrets
                # never enter the generated Blender program or child process environment.
                # Consume tokens as they arrive, so long programs do not need a
                # single idle HTTP response from the service or its reverse proxy.
                with httpx.stream("POST", url, headers={"Authorization": "Bearer " + (config.get("api_key") or "local")},
                    json={"model": config["model"], "messages": messages, "stream": True, "response_format": {"type": "json_object"}},
                    trust_env=urlparse(url).hostname not in ("localhost", "127.0.0.1", "::1"),
                    timeout=httpx.Timeout(120, connect=25)) as response:
                    if response.status_code in (401, 403):
                        raise ModelingError("大模型服务拒绝了密钥，请检查设置中的密钥和模型权限。", code="blender_ai_auth")
                    if response.status_code == 429:
                        raise ModelingError("大模型服务额度不足或请求过多，请稍后重试。", code="blender_ai_quota")
                    if response.status_code in (404, 405):
                        errors.append(f"服务接口返回 {response.status_code}")
                        break
                    if response.status_code in (408, 502, 503, 504):
                        raise httpx.RemoteProtocolError(f"Provider temporarily unavailable ({response.status_code})")
                    if not response.is_success:
                        raise ModelingError(f"大模型服务返回 {response.status_code}，请检查模型名称和 JSON 输出支持。", code="blender_ai_response")
                    content = read_program_response(response, cancelled)
            except httpx.RequestError as error:
                # Log only the exception class, never provider response bodies or
                # exception strings which may contain request credentials.
                category = type(error).__name__
                logger.warning("Model connection interrupted: host=%s type=%s attempt=%s", urlparse(url).hostname, category, connection_attempt + 1)
                if cancelled():
                    return None
                if connection_attempt < 2:
                    if update:
                        update(stage=f"大模型连接短暂中断，正在重试 · 第 {connection_attempt + 1} 次")
                    if not wait_for_retry(cancelled, 2 * (connection_attempt + 1)):
                        return None
                    continue
                if isinstance(error, httpx.TimeoutException):
                    raise ModelingError("大模型服务响应超时，自动重试后仍未恢复。建模步骤已保留，可点击继续重试。", code="blender_ai_timeout") from None
                raise ModelingError(f"大模型连接中断，自动重试后仍未恢复（{category}）。建模步骤已保留，可点击继续重试。", code="blender_ai_connection") from None
            except (ModelingError, ScriptPolicyError):
                raise
            except (KeyError, ValueError, TypeError, AttributeError):
                raise ScriptPolicyError("大模型未返回包含 code 的有效 JSON，请重新输出完整建模程序。") from None
            if cancelled():
                return None
            try:
                if isinstance(content, list):
                    content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
                result = json.loads(content.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
                if not isinstance(result, dict) or not isinstance(result.get("code"), str):
                    raise ValueError()
                return {"name": str(result.get("name") or "Blender 创作")[:40], "summary": str(result.get("summary") or "")[:2000], "code": result["code"],
                        "review": str(result.get("review") or "")[:2000]}
            except (KeyError, ValueError, TypeError, AttributeError):
                raise ScriptPolicyError("大模型未返回包含 code 的有效 JSON，请重新输出完整建模程序。") from None
    raise ModelingError(errors[-1] if errors else "大模型服务暂不可用。", code="blender_ai_connection")


def collect_mesh(path):
    if path.stat().st_size > 40_000_000:
        raise ScriptPolicyError("生成网格过大，请减少细分层级。")
    data = json.loads(path.read_text("utf-8"))
    mesh = trimesh.Trimesh(vertices=data["vertices"], faces=data["faces"], process=True)
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals(multibody=False)
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
    if not mesh.is_watertight or not mesh.is_winding_consistent or not np.isfinite(mesh.vertices).all():
        raise ScriptPolicyError("模型存在开放边界或法线错误。请让自定义曲面封闭，并正确应用布尔运算。")
    parts = mesh.split(only_watertight=False)
    positives, negatives = [], []
    for part in parts:
        if abs(part.volume) < 1e-7:
            continue
        if part.volume < 0:
            part.invert()
            target = negatives
        else:
            target = positives
        # Keep close relief intersections distinct during the union. Premature
        # float32 rounding can collapse small edges in otherwise valid armor.
        solid = manifold.Manifold(manifold.Mesh64(np.ascontiguousarray(part.vertices, np.float64), np.ascontiguousarray(part.faces, np.uint64)))
        if solid.status() != manifold.Error.NoError:
            raise ScriptPolicyError("表面存在自相交或无效拓扑，请在 Blender 中修正网格或使用合适的体素重构。")
        target.append(solid)
    if not positives:
        raise ScriptPolicyError("没有正体积实体，请修正面方向和厚度。")
    solid = manifold.Manifold.batch_boolean(positives, manifold.OpType.Add)
    if negatives:
        solid = solid - manifold.Manifold.batch_boolean(negatives, manifold.OpType.Add)
    if solid.status() != manifold.Error.NoError or solid.is_empty():
        raise ScriptPolicyError("布尔合并未形成实体，请修正相交方式。")
    # Center before packing: translating afterwards would introduce another
    # float32 rounding step when exporting STL.
    bounds = solid.bounding_box()
    solid = solid.translate([-(bounds[0]+bounds[3])/2, -(bounds[1]+bounds[4])/2, -bounds[2]])
    # STL stores float32 positions. Re-import that representation through
    # Manifold once, so coincident vertices/zero-area triangles produced by the
    # conversion are resolved before topology checks and file export.
    raw = solid.to_mesh()
    packed = manifold.Mesh(np.array(raw.vert_properties, dtype=np.float32, copy=True), np.array(raw.tri_verts, dtype=np.uint32, copy=True))
    packed.merge()
    solid = manifold.Manifold(packed)
    if solid.status() != manifold.Error.NoError or solid.is_empty():
        raise ScriptPolicyError("模型转为打印文件精度时出现退化表面，请修正过近的细节或相切面。")
    raw = solid.to_mesh()
    mesh = trimesh.Trimesh(vertices=np.asarray(raw.vert_properties)[:, :3], faces=np.asarray(raw.tri_verts), process=True)
    components = sum(part.volume > 1e-7 for part in mesh.split(only_watertight=False))
    if components != 1:
        raise ScriptPolicyError(f"有 {components} 个分离实体。请将全部保留部件相连，或用一体底座连接，不能只删除用户要求的部件。")
    if mesh.volume <= 0 or not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ScriptPolicyError("未通过正体积封闭实体检查，请修正模型。")
    if np.max(mesh.extents) > 500 or np.min(mesh.extents) < .5:
        raise ScriptPolicyError("尺寸异常。请以毫米建模，外廓控制在 0.5–500 mm，不要使用米或缩放 0.001。")
    warnings = ["已检查网格封闭性、正体积和连通性；壁厚、支撑、装配间隙和承载仍需在切片与试印中确认。"]
    if max(mesh.extents) > 250:
        warnings.append("模型某一方向超过 250 mm，请确认打印机的成型空间。")
    return mesh, {"dimensions": [round(float(value), 2) for value in mesh.extents], "volume_cm3": round(float(mesh.volume) / 1000, 3),
                  "triangles": len(mesh.faces), "watertight": True, "components": 1, "warnings": warnings, "units": "mm"}


def validate_dimensions(prompt, stats):
    text = prompt.lower()
    # Only check dimensions that clearly refer to the overall model. A feature
    # such as "立柱高40" or "槽宽8" must not become an outer-size constraint.
    def dimension(names):
        boundary = r"(?<![\u4e00-\u9fffA-Za-z])"
        prefixes = ("整体", "总体", "外廓", "模型", "成品", "")
        return number(text, [boundary + prefix + name for prefix in prefixes for name in names])
    labels = [("总宽", "外径", "宽度", "宽", "width"), ("总深", "深度", "深", "depth"), ("总高", "高度", "高", "height")]
    expected = [dimension(names) for names in labels]
    length = dimension(("总长", "长度", "长", "length"))
    if length is not None:
        if expected[0] is not None and expected[1] is None:
            expected[1] = expected[0]
        expected[0] = length
    for axis, (target, actual) in enumerate(zip(expected, stats["dimensions"])):
        if target is not None and abs(actual - target) > max(.2, abs(target) * .01):
            raise ScriptPolicyError(f"{'宽深高'[axis]}度与用户要求不符：实际 {actual} mm，要求 {target} mm。请修改建模步骤以保持该外廓尺寸，并保留设计特征。")


def memory_usage(process):
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    values = Counters()
    values.cb = ctypes.sizeof(values)
    if ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(int(process._handle)), ctypes.byref(values), values.cb):
        return max(values.WorkingSetSize, values.PagefileUsage)
    return 0


def run_blender(program, folder, cancelled, height=None, timeout=150):
    executable = find_blender()
    if executable is None:
        raise ModelingError("尚未安装 Blender。请运行「安装Blender建模.cmd」后重试。", code="blender_not_ready")
    validate_script(program["code"])
    folder.mkdir(parents=True, exist_ok=True)
    request = folder / "input.json"
    request.write_text(json.dumps({**program, "height": height}, ensure_ascii=False), "utf-8")
    environment = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATH", "TEMP", "TMP")}
    for name in ("BLENDER_USER_CONFIG", "BLENDER_USER_SCRIPTS", "BLENDER_USER_DATAFILES", "APPDATA", "LOCALAPPDATA", "USERPROFILE"):
        directory = folder / name.lower()
        directory.mkdir(exist_ok=True)
        environment[name] = str(directory)
    with (folder / "blender.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(executable), "--background", "--factory-startup", "--disable-autoexec", "--threads", "2",
            "--python-exit-code", "7", "--python", str(ROOT / "server" / "blender_worker.py"), "--", str(request), str(folder)],
            cwd=folder, env=environment, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancelled():
                    return None
                if time.monotonic() - started > timeout:
                    raise ScriptPolicyError("Blender 计算超过 150 秒。请简化布尔或细分，降低网格复杂度后再试。")
                if memory_usage(process) > 2_000_000_000:
                    raise ScriptPolicyError("Blender 建模内存超过 2 GB。请使用更粗的体素或减少细分和布尔复杂度。")
                time.sleep(.35)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
    if cancelled():
        return None
    try:
        result = json.loads((folder / "result.json").read_text("utf-8"))
    except (OSError, ValueError):
        raise ScriptPolicyError("Blender 异常结束。请减少模型复杂度，不要调用窗口或图形界面功能。") from None
    if not result.get("ok") or process.returncode:
        raise ScriptPolicyError(result.get("error", "Blender 建模失败。")[-6000:])
    mesh, stats = collect_mesh(folder / "mesh.json")
    return mesh, stats, result


def retry_folder(job_id):
    if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ModelingError("找不到可继续的建模记录，请重新生成。", code="blender_retry_missing")
    return ROOT / ".runtime" / "blender" / job_id


def retry_request(job_id):
    folder = retry_folder(job_id)
    try:
        if (folder / "request.json").is_file():
            return json.loads((folder / "request.json").read_text("utf-8"))
        # Compatibility with jobs created before conversation checkpoints.
        saved = json.loads((folder / "attempt-1" / "input.json").read_text("utf-8"))
        return {"prompt": saved["prompt"], "engine": "blender"}
    except (OSError, ValueError, KeyError):
        raise ModelingError("找不到完整的建模记录，请保留描述重新生成。", code="blender_retry_missing") from None


def retry_conversation(job_id):
    folder = retry_folder(job_id)
    if (folder / "conversation.json").is_file():
        return json.loads((folder / "conversation.json").read_text("utf-8"))
    saved = json.loads((folder / "attempt-1" / "input.json").read_text("utf-8"))
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": saved["prompt"]}]
    attempt = 0
    for i in range(1, 4):
        source, failure = folder / f"attempt-{i}" / "input.json", folder / f"failure-{i}.txt"
        if not source.is_file() or not failure.is_file():
            break
        program = json.loads(source.read_text("utf-8"))
        messages.extend([{"role": "assistant", "content": json.dumps({key: program[key] for key in ("name", "summary", "code")}, ensure_ascii=False)},
                         {"role": "user", "content": "Local Blender validation FAILED. Preserve the design and fix the underlying problem. Return complete corrected JSON. Failure:\n" + failure.read_text("utf-8")}])
        attempt = i
    return {"messages": messages, "attempt": attempt}


def recover_valid_attempt(job_id, prompt):
    """Recheck saved geometry after validator fixes without another paid call."""
    folder = retry_folder(job_id)
    for output in sorted(folder.glob('attempt-*'), reverse=True):
        try:
            program = json.loads((output / 'input.json').read_text('utf-8'))
            runtime = json.loads((output / 'result.json').read_text('utf-8'))
            if not runtime.get('ok') or not (output / 'model.blend').is_file():
                continue
            mesh, stats = collect_mesh(output / 'mesh.json')
            validate_dimensions(prompt, stats)
            return program, (mesh, stats, runtime), output
        except (OSError, ValueError, ScriptPolicyError):
            continue
    return None


def request_cancellable(config, messages, cancelled, update, started, job_id):
    """Let the user cancel even when a provider has not sent its next token."""
    import threading
    result = {}
    def request():
        try:
            result["program"] = request_program(config, list(messages), cancelled, update)
        except Exception as error:
            result["error"] = error
    thread = threading.Thread(target=request, name=f"blender-ai-{job_id[:8]}", daemon=True)
    thread.start()
    while thread.is_alive():
        if cancelled():
            return None
        update(elapsed_seconds=round(time.monotonic() - started))
        thread.join(.5)
    if "error" in result:
        raise result["error"]
    return result.get("program")


def failure_content(reason, output, cancelled):
    """Let repair see lost forms as well as a topology error, when a mesh exists."""
    text = "Local Blender execution or printable-mesh validation FAILED. Fix the underlying problem and return complete corrected JSON. Failure:\n" + reason
    source = output / "mesh.json"
    try:
        if not source.is_file() or source.stat().st_size > 40_000_000:
            return text
        raw = json.loads(source.read_text("utf-8"))
        mesh = trimesh.Trimesh(vertices=raw["vertices"], faces=raw["faces"], process=False)
        if not np.isfinite(mesh.vertices).all() or len(mesh.faces) > 500_000:
            return text
        picture = model_views(mesh, output / "failed-views.png", cancelled)
        if picture:
            return [{"type": "text", "text": text + "\nAttached are views of the FAILED geometry; it may be incomplete. Check for missing body volumes and detached details. Restore ALL requested features; do not delete them to pass validation. Monochrome shading omits colors."},
                    {"type": "image_url", "image_url": {"url": picture}}]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass
    return text


def polish(body, program, result, output, messages, folder, config, update, cancelled, started, job_id, checkpoint=None):
    """One visual refinement with at most one technical repair; keep valid draft on failure."""
    baseline = (program, result, output)
    try:
        update(progress=62, stage="正在从三个角度检查造型细节")
        picture = model_views(result[0], folder / "review-before.png", cancelled)
        if picture is None:
            return None
        if checkpoint:
            messages = checkpoint["messages"]
        else:
            messages = [*messages, {"role": "assistant", "content": json.dumps(program, ensure_ascii=False)},
                {"role": "user", "content": [
                    {"type": "text", "text": "These three shaded views show the ACTUAL printable mesh produced by your program, not a reference image. Views are FRONT(-Y), RIGHT(+X), THREE-QUARTER. Monochrome shading omits materials; do not interpret the missing colors as a modeling error. Review the user's description and inspect silhouette, continuous form, recognizable anatomy/features and missing physical details. Improve the most important 3–5 weaknesses in the EXISTING design, keeping the pose and functional interfaces. Do not just increase subdivisions. Keep specified dimensions and actual voids. Avoid disconnected decorative parts. If already fully appropriate (especially simple functional parts), return the identical code. Return complete JSON {name,summary,review,code}; review is a concise Chinese account of visible issues and the geometric corrections or why no changes are needed. Do not claim physical testing or measurements from the image.\nActual outer dimensions (mm): " + json.dumps(result[1]["dimensions"])},
                    {"type": "image_url", "image_url": {"url": picture}},
                ]}]
        first_attempt = checkpoint.get("attempt", 0) if checkpoint else 0
        for attempt in range(first_attempt, 2):
            if cancelled():
                return None
            # Retain the valid starting program so a manually resumed checkpoint
            # can rebuild it locally before continuing visual refinement.
            (folder / "conversation.json").write_text(json.dumps({"messages": messages, "attempt": attempt, "phase": "refine", "baseline": program}, ensure_ascii=False), "utf-8")
            update(progress=67 + attempt * 9, stage="大模型正在检查外观并精修" if not attempt else "正在修正精修模型的网格")
            refined = None
            try:
                refined = request_cancellable(config, messages, cancelled, update, started, job_id)
                if refined is None or cancelled():
                    return None
                if refined["code"].strip() == program["code"].strip():
                    return program, result, output, "reviewed", refined.get("review", "")
                validate_script(refined["code"])
                update(progress=80 + attempt * 5, stage="本地 Blender 正在制作精细结构")
                refined_output = folder / f"refine-{attempt + 1}"
                revised = run_blender({**refined, "prompt": body.prompt}, refined_output, cancelled)
                if revised is None or cancelled():
                    return None
                validate_dimensions(body.prompt, revised[1])
                # A refinement must also respect any clearly specified original
                # outer dimensions that still match the accepted current design.
                for description in [(body.previous or {}).get("prompt", "")]:
                    try:
                        validate_dimensions(description, result[1])
                    except ScriptPolicyError:
                        continue
                    validate_dimensions(description, revised[1])
                update(progress=91, stage="正在保存精修后的多角度预览")
                model_views(revised[0], folder / "review-after.png", cancelled)
                if cancelled():
                    return None
                return refined, revised, refined_output, "refined", refined.get("review", "")
            except ScriptPolicyError as error:
                reason = str(error)[-6500:]
                (folder / f"refine-failure-{attempt + 1}.txt").write_text(reason, "utf-8")
                if refined:
                    messages.append({"role": "assistant", "content": json.dumps(refined, ensure_ascii=False)})
                messages.append({"role": "user", "content": failure_content(reason, folder / f"refine-{attempt + 1}", cancelled)})
        warning = "精修版未通过网格检查，已保留本次通过检查的初版；可以点击「精修当前作品」继续。"
    except (ModelingError, ScriptPolicyError) as error:
        if cancelled():
            return None
        warning = f"外观精修未完成，已保留本次通过检查的初版。{error}"
    except (OSError, ValueError) as error:
        # Preview failure must not throw away a valid, printable model.
        logger.warning("Visual review unavailable: %s", type(error).__name__)
        warning = "多角度预览暂未完成，已保留本次通过检查的初版；可以稍后精修。"
    if cancelled():
        return None
    baseline[1][1]["warnings"].append(warning)
    return *baseline, "retained", warning


def generate(body, job_id, config, update, cancelled):
    if find_blender() is None:
        raise ModelingError("本地 Blender 尚未准备好，请运行「安装Blender建模.cmd」。", code="blender_not_ready")
    previous = body.previous or {}
    reusable = previous.get("kind") == "blender" and body.prompt == previous.get("prompt") and not body.regenerate and not body.resume_job
    if not reusable and not status(config)["configured"]:
        raise ModelingError("请在设置中开启大模型服务，填写服务地址、模型和密钥。Blender 在本地执行建模。", code="blender_ai_not_configured")
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + (FINE_PROMPT if body.detail == "fine" else DRAFT_PROMPT)}]
    if previous.get("kind") == "blender":
        messages.append({"role": "user", "content": "Current editable design; preserve it except for the requested changes:\n" + json.dumps({key: previous.get(key) for key in ("name", "prompt", "edits", "code", "summary", "params")}, ensure_ascii=False)[:75000]})
    messages.append({"role": "user", "content": sketch_content(body)})
    folder = ROOT / ".runtime" / "blender" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "request.json").write_text(json.dumps(body.model_dump(exclude={"resume_job"}), ensure_ascii=False), "utf-8")
    first_attempt = 0
    review_checkpoint = None
    recovered = None
    if body.resume_job:
        checkpoint = retry_conversation(body.resume_job)
        messages = checkpoint["messages"]
        first_attempt = checkpoint["attempt"]
        if checkpoint.get("phase") == "refine":
            review_checkpoint = checkpoint
            first_attempt = 0
        elif first_attempt >= 3:
            update(progress=10, stage='正在重新检查已保留的细节模型')
            recovered = recover_valid_attempt(body.resume_job, body.prompt)
            first_attempt = 0
            if recovered:
                messages.append({'role': 'user', 'content': 'A previously failed attempt now passes the corrected host validator. Continue from that exact program and actual geometry below; do not simplify the requested design.'})
    started = time.monotonic()
    failures = []
    program = None
    if recovered:
        program = recovered[0]
    if review_checkpoint:
        program = review_checkpoint["baseline"]
    # Explicit parameter edits can reuse code without another paid model call.
    if reusable:
        program = {key: previous.get(key, "") for key in ("name", "summary", "code")}
    for attempt in range(first_attempt, 3):
        if cancelled():
            return None
        try:
            if program is None:
                (folder / "conversation.json").write_text(json.dumps({"messages": messages, "attempt": attempt}, ensure_ascii=False), "utf-8")
                update(progress=15 + attempt * (12 if body.detail == "fine" else 20), stage="大模型正在设计建模步骤" if not attempt else f"大模型正在修正建模步骤 · 第 {attempt} 次", attempts=attempt + 1)
                program = request_cancellable(config, messages, cancelled, update, started, job_id)
                if program is None:
                    return None
            validate_script(program["code"])
            update(progress=35 + attempt * (10 if body.detail == "fine" else 20), stage="本地 Blender 正在建模" if not attempt else "本地 Blender 正在重新建模", attempts=attempt + 1)
            output = folder / f"attempt-{attempt + 1}"
            height = body.params.get("height") if reusable else None
            if recovered:
                _, result, output = recovered
                recovered = None
            else:
                result = run_blender({**program, "prompt": body.prompt}, output, cancelled, height)
            if result is None:
                return None
            mesh, stats, runtime = result
            if not reusable:
                validate_dimensions(body.prompt, stats)
            refinement, review = "skipped", ""
            if body.detail == "fine" and not reusable:
                polished = polish(body, program, result, output, messages, folder, config, update, cancelled, started, job_id, review_checkpoint)
                if polished is None:
                    return None
                program, result, output, refinement, review = polished
                mesh, stats, runtime = result
            if cancelled():
                return None
            update(progress=94, stage="打印网格检查已通过，保存 Blender 工程")
            (folder / "program.py").write_text(program["code"], "utf-8")
            stats["generation_seconds"] = round(time.monotonic() - started, 1)
            if program["summary"]:
                stats["warnings"].append(program["summary"])
            recipe = {"kind": "blender", "category": "generative", "name": program["name"], "prompt": previous.get("prompt", body.prompt) if previous else body.prompt,
                      "params": {"height": float(stats["dimensions"][2])}, "code": program["code"], "summary": program["summary"],
                      "edits": [*previous.get("edits", [])[-29:], body.prompt] if previous and body.prompt != previous.get("prompt") else previous.get("edits", []),
                      "generator": "LLM + local Blender", "blender_version": runtime.get("blender_version"), "attempts": attempt + 1}
            recipe.update(detail=previous.get("detail", body.detail) if reusable else body.detail,
                          refinement=previous.get("refinement", "skipped") if reusable else refinement,
                          review=previous.get("review", "") if reusable else review)
            if body.sketch or previous.get("sketch"):
                recipe["sketch"] = body.sketch or previous["sketch"]
            if body.reference or previous.get('reference'):
                recipe['reference'] = body.reference or previous['reference']
            return recipe, mesh, stats, output / "model.blend", folder / "program.py"
        except ScriptPolicyError as error:
            reason = str(error)[-6500:]
            failures.append(reason)
            if program:
                messages.append({"role": "assistant", "content": json.dumps(program, ensure_ascii=False)})
            feedback = failure_content(reason, folder / f"attempt-{attempt + 1}", cancelled) if body.detail == "fine" and not reusable else "Local Blender execution or printable-mesh validation FAILED. Fix the underlying problem and return complete corrected JSON. Failure:\n" + reason
            messages.append({"role": "user", "content": feedback})
            (folder / f"failure-{attempt + 1}.txt").write_text(reason, "utf-8")
            (folder / "conversation.json").write_text(json.dumps({"messages": messages, "attempt": attempt + 1}, ensure_ascii=False), "utf-8")
            if reusable:
                raise ModelingError("本地重建未通过网格检查，已有作品不受影响。可继续用文字提出修改，或打开 Blender 工程检查。", code="blender_local_rebuild_failed") from None
            program = None
    raise ModelingError("模型已保留，但打印网格检查尚未通过。可点击「继续修复」沿用现有设计，不必重新描述。最后发现的问题：" + (failures[-1][:350] if failures else '模型需要进一步修复。'), code="blender_validation_failed")
