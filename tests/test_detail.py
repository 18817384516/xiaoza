import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from server import blender_bridge as bridge
from server.app import GenerateRequest
from server.blender_policy import ScriptPolicyError
from server.model_views import model_views
from server.modeling import ModelingError
from tests.test_blender import PROGRAM, CONFIG


@pytest.fixture
def modeler(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, 'ROOT', tmp_path)
    monkeypatch.setattr(bridge, 'find_blender', lambda: Path('blender.exe'))
    calls = []
    def run(program, folder, cancelled, height=None):
        calls.append(program)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'model.blend').write_bytes(b'test')
        mesh = trimesh.creation.box([40, 30, 8])
        return mesh, {'dimensions': [40, 30, 8], 'warnings': [], 'watertight': True}, {'blender_version': 'test'}
    monkeypatch.setattr(bridge, 'run_blender', run)
    return calls


def generate(tmp_path, request=None):
    return bridge.generate(request or GenerateRequest(prompt='总宽40毫米，深30毫米，高8毫米', engine='blender'),
                           'd' * 32, {**CONFIG, 'enabled': True}, lambda **v: None, lambda: False)


def test_fine_review_receives_actual_mesh_images_and_preserves_updated_program(tmp_path, monkeypatch, modeler):
    calls = []
    def request(config, messages, cancelled, update):
        calls.append(messages)
        if len(calls) == 1:
            assert 'QUALITY: FINE' in messages[0]['content']
            return {'code': PROGRAM, 'name': '结构件', 'summary': '基础造型'}
        assert 'ACTUAL printable mesh' in messages[-1]['content'][0]['text']
        assert messages[-1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
        assert json.loads(messages[-2]['content'])['code'] == PROGRAM
        return {'code': PROGRAM + '\n# Useful refinement', 'name': '结构件', 'summary': '精细结构', 'review': '检查并保留通孔'}
    monkeypatch.setattr(bridge, 'request_program', request)
    result = generate(tmp_path)
    assert len(calls) == len(modeler) == 2
    assert result[0]['refinement'] == 'refined' and result[0]['detail'] == 'fine'
    assert result[0]['review'] == '检查并保留通孔'
    assert result[3].parent.name == 'refine-1'
    assert (result[4].parent / 'review-before.png').is_file()
    assert (result[4].parent / 'review-after.png').is_file()


@pytest.mark.parametrize('failure', ['connection', 'geometry', 'dimensions'])
def test_failed_refinement_keeps_valid_baseline(tmp_path, monkeypatch, modeler, failure):
    calls = []
    def request(config, messages, cancelled, update):
        calls.append(messages)
        if len(calls) == 1:
            return {'code': PROGRAM, 'name': '结构件', 'summary': ''}
        if failure == 'connection':
            raise ModelingError('连接中断', code='blender_ai_connection')
        return {'code': PROGRAM + '\n# Refined', 'name': '结构件', 'summary': ''}
    original = bridge.run_blender
    def run(program, *args):
        if program['code'] != PROGRAM and failure == 'geometry':
            raise ScriptPolicyError('精修产生分离实体')
        result = original(program, *args)
        if program['code'] != PROGRAM and failure == 'dimensions':
            result[1]['dimensions'] = [44, 30, 8]
        return result
    monkeypatch.setattr(bridge, 'run_blender', run)
    monkeypatch.setattr(bridge, 'request_program', request)
    result = generate(tmp_path)
    assert result[0]['code'] == PROGRAM and result[0]['refinement'] == 'retained'
    assert result[1].is_watertight and result[3].parent.name == 'attempt-1'
    assert any('保留' in warning for warning in result[2]['warnings'])
    assert len(calls) == (2 if failure == 'connection' else 3)


def test_no_change_review_avoids_rebuilding_and_local_resize_never_requests_review(tmp_path, monkeypatch, modeler):
    calls = []
    def request(*args):
        calls.append(1)
        return {'code': PROGRAM, 'name': '结构件', 'summary': '', 'review': '造型符合要求'}
    monkeypatch.setattr(bridge, 'request_program', request)
    result = generate(tmp_path)
    assert result[0]['refinement'] == 'reviewed' and len(modeler) == 1 and len(calls) == 2
    previous = result[0]
    local = generate(tmp_path, GenerateRequest(prompt=previous['prompt'], previous=previous, params={'height': 8}))
    assert len(calls) == 2 and local[0]['refinement'] == 'reviewed'


def test_example_import_and_local_resize_need_no_cloud_configuration(tmp_path, monkeypatch, modeler):
    def forbidden(*args, **kwargs):
        pytest.fail('Local example import must not call an AI service')
    monkeypatch.setattr(bridge, 'request_program', forbidden)
    previous = {'kind': 'blender', 'name': '离线示例', 'prompt': '带通孔的结构件',
                'code': PROGRAM, 'summary': '保存的程序', 'params': {'height': 8}}
    result = bridge.generate(GenerateRequest(prompt=previous['prompt'], previous=previous, params={'height': 8}),
                             'e' * 32, {'enabled': False}, lambda **v: None, lambda: False)
    assert result[0]['name'] == previous['name'] and len(modeler) == 1


def test_cancel_during_review_does_not_publish_draft_or_start_blender(tmp_path, monkeypatch, modeler):
    stopped = False
    def request(*args):
        nonlocal stopped
        stopped = True
        return {'code': PROGRAM, 'name': '结构件', 'summary': ''}
    monkeypatch.setattr(bridge, 'request_program', request)
    previous = {'code': PROGRAM, 'name': '结构件', 'summary': ''}
    mesh = trimesh.creation.box()
    output = tmp_path / 'attempt-1'
    result = bridge.polish(GenerateRequest(prompt='结构件'), previous, (mesh, {'dimensions': [1,1,1], 'warnings': []}, {}), output,
                           [], tmp_path, CONFIG, lambda **v: None, lambda: stopped, 0, 'x')
    assert result is None and len(modeler) == 0


def test_multiview_preview_contains_geometry_and_honors_cancellation(tmp_path):
    from base64 import b64decode
    from io import BytesIO
    from PIL import Image
    mesh = trimesh.creation.box([40, 30, 8])
    encoded = model_views(mesh, tmp_path / 'views.png')
    with Image.open(BytesIO(b64decode(encoded.split(',', 1)[1]))) as picture:
        pixels = np.asarray(picture)
        assert picture.size == (1536, 554)
        for i in range(3):
            panel = pixels[42:, i*512:(i+1)*512]
            assert np.sum(np.any(panel != [241,242,245], axis=2)) > 5000
    assert model_views(mesh, cancelled=lambda: True) is None


def test_failed_geometry_is_visible_to_repair_and_missing_mesh_is_text_only(tmp_path):
    assert isinstance(bridge.failure_content('尺寸不符', tmp_path, lambda: False), str)
    mesh = trimesh.creation.box([40, 30, 8])
    (tmp_path / 'mesh.json').write_text(json.dumps({'vertices': mesh.vertices.tolist(), 'faces': mesh.faces.tolist()}), 'utf-8')
    content = bridge.failure_content('尺寸不符', tmp_path, lambda: False)
    assert '尺寸不符' in content[0]['text'] and 'FAILED geometry' in content[0]['text']
    assert content[1]['image_url']['url'].startswith('data:image/png;base64,')


def test_resume_visual_review_rebuilds_the_baseline_and_keeps_review_context(tmp_path, monkeypatch, modeler):
    original_id = 'a' * 32
    saved = tmp_path / '.runtime' / 'blender' / original_id
    saved.mkdir(parents=True)
    messages = [{'role': 'user', 'content': 'Saved multi-view review and exact design context'}]
    baseline = {'name': '原结构', 'summary': '', 'code': PROGRAM}
    (saved / 'conversation.json').write_text(json.dumps({'messages': messages, 'attempt': 0, 'phase': 'refine', 'baseline': baseline}), 'utf-8')
    calls = []
    def request(config, actual, cancelled, update):
        calls.append(actual)
        assert actual == messages
        return {**baseline, 'code': PROGRAM + '\n# Retained refinement'}
    monkeypatch.setattr(bridge, 'request_program', request)
    result = generate(tmp_path, GenerateRequest(prompt='总宽40毫米，深30毫米，高8毫米', engine='blender', resume_job=original_id))
    assert result[0]['refinement'] == 'refined'
    assert len(calls) == 1 and len(modeler) == 2
