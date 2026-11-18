import json
from pathlib import Path
import threading
import time

import numpy as np
import pytest

from server.blender_policy import ScriptPolicyError, validate_script
from server import blender_bridge as bridge


PROGRAM = '''import bpy
def create_model():
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,4))
    block = bpy.context.object
    block.name = 'Slotted test part'
    block.dimensions = (40,30,8)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=4, depth=12, location=(0,0,4))
    cutter = bpy.context.object
    bpy.context.view_layer.objects.active = block
    modifier = block.modifiers.new('Real through hole', 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.solver = 'EXACT'
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return [block]
'''


@pytest.mark.parametrize('fragment', [
    "import os", "import bpy as operating", "open('secret')", "eval('1')", "getattr(bpy, 'app')",
    "bpy.app.handlers.load_post.clear()", "bpy.ops.wm.open_mainfile(filepath='x')",
    "bpy.data.texts.new('x')", "bpy.context.scene.render.filepath='x'", "x = 'a.__class__'",
    "from pathlib import Path", "from math import __dict__", "while True: pass",
    "from bpy import app as application",
])
def test_generated_program_has_only_modeling_access(fragment):
    with pytest.raises(ScriptPolicyError):
        validate_script(PROGRAM + '\n' + fragment)


def test_custom_modeling_script_is_allowed():
    assert validate_script(PROGRAM)


def test_provider_root_url_uses_v1_endpoint():
    assert bridge.endpoints('https://example.com') == ['https://example.com/v1/chat/completions', 'https://example.com/chat/completions']
    assert bridge.endpoints('https://example.com/v1/') == ['https://example.com/v1/chat/completions']


def test_stated_outer_dimensions_are_checked_and_wrong_sizes_request_revision():
    bridge.validate_dimensions('总宽36毫米，深20毫米，高28毫米', {'dimensions':[36,20,28]})
    with pytest.raises(ScriptPolicyError, match='与用户要求不符'):
        bridge.validate_dimensions('总宽36毫米，深20毫米，高28毫米', {'dimensions':[40,20,28]})


def test_feature_dimensions_do_not_override_the_whole_model():
    bridge.validate_dimensions('底板厚3毫米，立柱高40毫米，槽宽8毫米', {'dimensions': [36,20,43]})
    with pytest.raises(ScriptPolicyError, match='要求 70'):
        bridge.validate_dimensions('小猫的耳朵高度10毫米，整体高度70毫米', {'dimensions': [40,30,65]})


def test_sketch_is_sent_as_an_image_reference_with_the_description():
    from server.app import GenerateRequest
    from base64 import b64decode
    from io import BytesIO
    from PIL import Image
    content = bridge.sketch_content(GenerateRequest(prompt='按草图做一把椅子', sketch=[[[20,30],[180,40],[170,190]]]))
    assert content[0]['text'].startswith('按草图做一把椅子')
    picture = content[1]['image_url']['url']
    assert picture.startswith('data:image/png;base64,')
    with Image.open(BytesIO(b64decode(picture.split(',',1)[1]))) as image:
        assert image.size == (640,420)
        assert image.getpixel((20,30)) != (255,255,255)


@pytest.mark.skipif(bridge.find_blender() is None, reason='Blender is not installed')
def test_real_blender_mesh_hole_units_and_editable_file(tmp_path):
    output = bridge.run_blender({'code': PROGRAM, 'summary': '真实通孔测试', 'prompt': '40x30x8 mm part'}, tmp_path, lambda: False)
    mesh, stats, result = output
    assert mesh.is_watertight and mesh.volume > 0
    assert stats['components'] == 1 and stats['units'] == 'mm'
    assert np.allclose(mesh.extents, [40,30,8], atol=.001)
    assert 40*30*8 - np.pi*4**2*8 == pytest.approx(mesh.volume, rel=.001)
    assert (tmp_path / 'model.blend').stat().st_size > 10000
    assert result['blender_version'].startswith('4.5')


@pytest.mark.skipif(bridge.find_blender() is None, reason='Blender is not installed')
def test_real_blender_dimension_edit_preserves_hole(tmp_path):
    mesh, stats, _ = bridge.run_blender({'code': PROGRAM}, tmp_path, lambda: False, height=16)
    assert np.allclose(mesh.extents, [80,60,16], atol=.001)
    assert mesh.volume < 80*60*16


@pytest.mark.skipif(bridge.find_blender() is None, reason='Blender is not installed')
def test_automatic_revision_uses_actual_blender_error(tmp_path, monkeypatch):
    from server.app import GenerateRequest
    programs = [
        {'name': '测试', 'summary': '', 'code': 'import bpy\ndef create_model():\n    return []\n'},
        {'name': '通孔结构', 'summary': '保留真实通孔', 'code': PROGRAM},
    ]
    def request(config, messages, cancelled, update=None):
        if len(programs) == 1:
            assert 'must return a list' in messages[-1]['content']
        return programs.pop(0)
    monkeypatch.setattr(bridge, 'request_program', request)
    states = []
    result = bridge.generate(GenerateRequest(prompt='一个带通孔的新结构', engine='blender', detail='draft'), 'test-repair-' + tmp_path.name,
        {'enabled': True, 'base_url': 'https://example.com/v1', 'model': 'test', 'api_key': 'test'},
        lambda **state: states.append(state), lambda: False)
    assert result[0]['attempts'] == 2
    assert result[1].is_watertight
    assert any('修正' in state.get('stage','') for state in states)


def test_ai_error_never_runs_blender(monkeypatch):
    import httpx
    from contextlib import contextmanager
    @contextmanager
    def stream(*args, **kwargs):
        yield httpx.Response(401)
    monkeypatch.setattr(bridge.httpx, 'stream', stream)
    from server.modeling import ModelingError
    with pytest.raises(ModelingError, match='密钥'):
        bridge.request_program({'base_url':'https://example.com/v1','api_key':'bad','model':'test'}, [], lambda: False)


@pytest.fixture
def provider(monkeypatch):
    from contextlib import contextmanager
    import httpx
    calls = []
    def install(responses):
        @contextmanager
        def stream(method, url, **kwargs):
            calls.append({'method': method, 'url': url, **kwargs})
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            try:
                yield item
            finally:
                item.close()
        monkeypatch.setattr(bridge.httpx, 'stream', stream)
        monkeypatch.setattr(bridge, 'wait_for_retry', lambda cancelled, delay: not cancelled())
        return calls
    return install


CONFIG = {'base_url': 'https://example.com/v1', 'api_key': 'test-secret', 'model': 'test'}


def stream_response(complete=True):
    import httpx
    content = json.dumps({'name': '流式通孔', 'summary': '', 'code': PROGRAM}, ensure_ascii=False)
    lines = ['data: ' + json.dumps({'choices': [{'delta': {'content': content[i:i+9]}, 'finish_reason': None}]}, ensure_ascii=False) + '\n\n'
             for i in range(0, len(content), 9)]
    if complete:
        lines += ['data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n', 'data: [DONE]\n\n']
    raw = ''.join(lines).encode('utf-8')
    class Bytes(httpx.SyncByteStream):
        def __iter__(self):
            for i in range(0,len(raw),17):
                yield raw[i:i+17]
    return httpx.Response(200, headers={'Content-Type': 'text/event-stream; charset=utf-8'}, stream=Bytes())


def test_streamed_program_handles_chunk_boundaries_and_unicode(provider):
    calls=provider([stream_response()])
    result=bridge.request_program(CONFIG, [], lambda: False)
    assert result['code']==PROGRAM and result['name']=='流式通孔'
    assert len(calls)==1 and calls[0]['json']['stream'] is True


def test_non_streaming_compatible_provider_still_works(provider):
    import httpx
    provider([httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'code': PROGRAM})}}]})])
    assert bridge.request_program(CONFIG,[],lambda: False)['code']==PROGRAM


def test_connection_drop_retries_the_same_conversation(provider):
    import httpx
    calls=provider([httpx.ConnectError('network'), stream_response()])
    states=[]
    messages=[{'role':'user','content':'保留孔位'}]
    assert bridge.request_program(CONFIG,messages,lambda: False,lambda **state: states.append(state))['code']==PROGRAM
    assert len(calls)==2 and calls[0]['json']==calls[1]['json']
    assert any('重试' in state['stage'] for state in states)


def test_truncated_stream_is_retried_even_if_its_json_looks_complete(provider):
    calls=provider([stream_response(complete=False), stream_response()])
    assert bridge.request_program(CONFIG,[],lambda: False)['code']==PROGRAM
    assert len(calls)==2


@pytest.mark.parametrize('status', [502,503,504])
def test_temporary_provider_failure_retries(provider,status):
    import httpx
    calls=provider([httpx.Response(status), stream_response()])
    assert bridge.request_program(CONFIG,[],lambda: False)['code']==PROGRAM
    assert len(calls)==2


def test_exhausted_timeouts_keep_specific_error_and_safe_logs(provider,caplog):
    import httpx
    from server.modeling import ModelingError
    calls=provider([httpx.ReadTimeout('test-secret') for _ in range(3)])
    with pytest.raises(ModelingError) as error:
        bridge.request_program(CONFIG,[],lambda: False)
    assert error.value.code=='blender_ai_timeout'
    assert len(calls)==3 and 'test-secret' not in caplog.text


def test_root_endpoint_fallback_and_auth_errors_are_not_retried(provider):
    import httpx
    from server.modeling import ModelingError
    calls=provider([httpx.Response(404),httpx.Response(403)])
    with pytest.raises(ModelingError) as error:
        bridge.request_program({**CONFIG,'base_url':'https://example.com'},[],lambda: False)
    assert error.value.code=='blender_ai_auth'
    assert len(calls)==2 and calls[1]['url']=='https://example.com/chat/completions'


def test_cancelling_retry_prevents_another_paid_request(provider,monkeypatch):
    import httpx
    calls=provider([httpx.ConnectError('offline')])
    monkeypatch.setattr(bridge,'wait_for_retry',lambda *args:False)
    assert bridge.request_program(CONFIG,[],lambda: False) is None
    assert len(calls)==1


def test_legacy_retry_recovers_the_program_and_failure_report(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,'ROOT',tmp_path)
    identifier='a'*32
    folder=tmp_path/'.runtime'/'blender'/identifier
    attempt=folder/'attempt-1'
    attempt.mkdir(parents=True)
    (attempt/'input.json').write_text(json.dumps({'name':'设计','summary':'','code':PROGRAM,'prompt':'原始瑞兽描述'}),'utf-8')
    (folder/'failure-1.txt').write_text('模型开放边界','utf-8')
    request=bridge.retry_request(identifier)
    conversation=bridge.retry_conversation(identifier)
    assert request['prompt']=='原始瑞兽描述' and conversation['attempt']==1
    assert json.loads(conversation['messages'][-2]['content'])['code']==PROGRAM
    assert '模型开放边界' in conversation['messages'][-1]['content']
    with pytest.raises(Exception):
        bridge.retry_request('../settings')


@pytest.mark.skipif(bridge.find_blender() is None, reason='Blender is not installed')
def test_resume_after_connection_failure_preserves_repair_context(tmp_path,monkeypatch):
    from server.app import GenerateRequest
    from server.modeling import ModelingError
    executable=bridge.find_blender()
    monkeypatch.setattr(bridge,'ROOT',tmp_path)
    # Keep the trusted worker path in this real-Blender test.
    original_run=bridge.run_blender
    project_root=Path(__file__).resolve().parent.parent
    def run(*args,**kwargs):
        monkeypatch.setattr(bridge,'ROOT',project_root)
        try: return original_run(*args,**kwargs)
        finally: monkeypatch.setattr(bridge,'ROOT',tmp_path)
    monkeypatch.setattr(bridge,'run_blender',run)
    monkeypatch.setattr(bridge,'find_blender',lambda: executable)
    calls=[]
    def request(config,messages,cancelled,update=None):
        calls.append(messages)
        if len(calls)==1:
            return {'name':'恢复测试','summary':'','code':'import bpy\ndef create_model():\n    return []\n'}
        if len(calls)==2:
            raise ModelingError('连接中断',code='blender_ai_connection')
        assert 'must return a list' in messages[-1]['content']
        return {'name':'恢复测试','summary':'','code':PROGRAM}
    monkeypatch.setattr(bridge,'request_program',request)
    identifier='b'*32
    config={**CONFIG,'enabled':True}
    with pytest.raises(ModelingError):
        bridge.generate(GenerateRequest(prompt='我的原创通孔结构',engine='blender',detail='draft'),identifier,config,lambda **v:None,lambda:False)
    restored=bridge.retry_request(identifier)
    result=bridge.generate(GenerateRequest(**restored,resume_job=identifier),'c'*32,config,lambda **v:None,lambda:False)
    assert result[0]['prompt']=='我的原创通孔结构'
    assert result[0]['attempts']==2 and result[1].is_watertight
    assert len(calls)==3 and calls[1]==calls[2]


def test_local_project_rebuild_never_silently_calls_paid_service(tmp_path,monkeypatch):
    from server.app import GenerateRequest
    from server.modeling import ModelingError
    monkeypatch.setattr(bridge,'ROOT',tmp_path)
    monkeypatch.setattr(bridge,'find_blender',lambda:Path('blender.exe'))
    def forbidden(*args,**kwargs):
        pytest.fail('A local parameter edit must not make a paid model request')
    monkeypatch.setattr(bridge,'request_program',forbidden)
    def fail(*args,**kwargs):
        raise ScriptPolicyError('模型开放边界')
    monkeypatch.setattr(bridge,'run_blender',fail)
    previous={'kind':'blender','name':'已保存设计','prompt':'原创造型','params':{},'code':PROGRAM,'summary':''}
    with pytest.raises(ModelingError) as error:
        bridge.generate(GenerateRequest(prompt='原创造型',previous=previous), 'local-rebuild-test', {**CONFIG,'enabled':True},lambda **v:None,lambda:False)
    assert error.value.code=='blender_local_rebuild_failed'
