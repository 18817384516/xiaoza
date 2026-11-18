import base64
import io
import json
from pathlib import Path
import struct

import httpx
import numpy as np
from PIL import Image
import pytest
import trimesh

from server import cloud3d, blender_bridge as bridge
from server.app import GenerateRequest, SettingsRequest, app, export_3mf
from server.modeling import ModelingError
from server.references import normalize_reference
from fastapi.testclient import TestClient


def picture():
    image = Image.new('RGB', (100, 160), '#998877')
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()


def asset(mesh=None):
    return trimesh.Scene(mesh or trimesh.creation.box([.4, 1, .3])).export(file_type='glb')


def test_reference_is_normalized_and_combined_with_description():
    reference = normalize_reference(picture())
    assert reference.startswith('data:image/jpeg;base64,')
    content = bridge.sketch_content(GenerateRequest(prompt='兵马俑雕像', reference=reference))
    assert content[0]['text'].startswith('兵马俑雕像')
    assert content[1]['image_url']['url'] == reference
    for invalid in ['https://example.com/image.png','data:image/svg+xml;base64,YQ==','data:image/png;base64,bad']:
        with pytest.raises(ModelingError):
            normalize_reference(invalid)


def test_detailed_armor_union_survives_stl_roundtrip(tmp_path):
    # A 2704-triangle crop of the user's failed model. Its close eyelid/head
    # intersection failed the old float32-first boolean pipeline.
    with np.load(Path(__file__).parent/'fixtures'/'armor-intersection.npz') as source:
        data = {key: source[key].tolist() for key in ('vertices','faces')}
    path = tmp_path/'mesh.json'
    path.write_text(json.dumps(data),'utf-8')
    mesh, stats = bridge.collect_mesh(path)
    restored = trimesh.load(io.BytesIO(mesh.export(file_type='stl')), file_type='stl')
    assert mesh.is_watertight and restored.is_watertight
    assert restored.is_winding_consistent and restored.volume > 0
    assert stats['components'] == 1
    restored_3mf = trimesh.load(io.BytesIO(export_3mf(restored)), file_type='3mf').to_geometry()
    assert restored_3mf.is_watertight and restored_3mf.is_winding_consistent


def test_3mf_preserves_nearby_vertices_instead_of_decimal_rounding():
    # Fine boolean intersections can create short valid edges even on a
    # large sculpture. The old six-decimal serialization collapsed them.
    mesh = trimesh.creation.box([4e-7, 1, 1])
    restored = trimesh.load(io.BytesIO(export_3mf(mesh)), file_type='3mf').to_geometry()
    assert restored.is_watertight and restored.volume > 0
    assert restored.extents == pytest.approx(mesh.extents)


def test_failed_detailed_model_resumes_from_retained_valid_geometry(tmp_path, monkeypatch):
    program_code = 'import bpy\ndef create_model():\n    bpy.ops.mesh.primitive_cube_add()\n    return [bpy.context.object]\n'
    monkeypatch.setattr(bridge, 'ROOT', tmp_path)
    monkeypatch.setattr(bridge, 'find_blender', lambda: Path('blender.exe'))
    monkeypatch.setattr(bridge, 'status', lambda config: {'configured': True})
    old_id = '1' * 32
    folder = tmp_path / '.runtime' / 'blender' / old_id
    output = folder / 'attempt-2'
    output.mkdir(parents=True)
    program = {'name': '保留甲片', 'summary': '原始设计', 'code': program_code}
    (output / 'input.json').write_text(json.dumps(program), 'utf-8')
    (output / 'result.json').write_text(json.dumps({'ok': True, 'blender_version': '4.5'}), 'utf-8')
    (output / 'model.blend').write_bytes(b'original-blend')
    with np.load(Path(__file__).parent / 'fixtures' / 'armor-intersection.npz') as source:
        (output / 'mesh.json').write_text(json.dumps({key: source[key].tolist() for key in ('vertices','faces')}), 'utf-8')
    (folder / 'conversation.json').write_text(json.dumps({'messages': [], 'attempt': 3}), 'utf-8')
    def forbidden(*args, **kwargs):
        pytest.fail('A valid retained mesh must not trigger another paid call or rebuild')
    monkeypatch.setattr(bridge, 'request_cancellable', forbidden)
    monkeypatch.setattr(bridge, 'run_blender', forbidden)
    result = bridge.generate(GenerateRequest(engine='blender', prompt='兵马俑', detail='draft', resume_job=old_id),
                             '2' * 32, {}, lambda **v: None, lambda: False)
    recipe, mesh, stats, blend, script = result
    assert recipe['code'] == program_code and recipe['name'] == '保留甲片'
    assert blend == output / 'model.blend' and blend.read_bytes() == b'original-blend'
    assert script.read_text('utf-8') == program_code
    assert mesh.is_watertight and stats['components'] == 1


def test_glb_with_external_uris_is_not_loaded(tmp_path):
    document = json.dumps({'asset':{'version':'2.0'},'buffers':[{'uri':'file:///private/local.file','byteLength':32}]}).encode()
    document += b' ' * (-len(document) % 4)
    raw = struct.pack('<4sII',b'glTF',2,len(document)+20) + struct.pack('<II',len(document),0x4e4f534a) + document
    path = tmp_path/'external.glb'
    path.write_bytes(raw)
    with pytest.raises(ModelingError):
        cloud3d.validate_glb(path)


def test_separate_clothing_is_retained_and_not_marked_printable(tmp_path):
    a = trimesh.creation.box([.4,1,.3])
    b = a.copy(); b.apply_translation([1,0,0])
    path=tmp_path/'original.glb'; path.write_bytes(trimesh.Scene([a,b]).export(file_type='glb'))
    mesh, stats=cloud3d.prepare_asset(path,120,tmp_path,lambda:False)
    assert stats['print_ready'] is False and stats['components']==2
    assert stats['triangles']==24 and len(mesh.split())==2
    assert mesh.extents[2]==pytest.approx(120)
    assert path.read_bytes().startswith(b'glTF')


def test_valid_asset_checks_and_scales_locally(tmp_path):
    path=tmp_path/'original.glb'; path.write_bytes(asset())
    mesh,stats=cloud3d.prepare_asset(path,120,tmp_path,lambda:False)
    assert stats['print_ready'] and stats['watertight'] and stats['components']==1
    assert mesh.extents[2]==pytest.approx(120)
    assert mesh.bounds[0,2]==0


def test_creation_is_not_retried_when_its_response_is_lost():
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('private-service-secret')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelingError) as error:
            cloud3d.api_request(client,'POST','/v1/image-to-3d',{'image_url':picture()})
    assert len(calls)==1 and error.value.code=='cloud3d_create_uncertain'
    assert 'private-service-secret' not in str(error.value)


@pytest.mark.parametrize('code',[401,403,402,429])
def test_service_errors_are_specific_without_disclosing_response(code):
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(code,text='secret'))) as client:
        with pytest.raises(ModelingError) as error:
            cloud3d.api_request(client,'GET','/v1/image-to-3d/task')
    assert error.value.code==('cloud3d_auth' if code in (401,403) else 'cloud3d_quota')
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('image,texture,expected_posts',[(True,True,1),(False,False,1),(False,True,2)])
def test_real_provider_contract_and_local_validation_without_charging(tmp_path,monkeypatch,image,texture,expected_posts):
    monkeypatch.setattr(cloud3d,'ROOT',tmp_path)
    calls=[]
    def request(client,method,path,payload=None):
        calls.append((method,path,payload))
        if method=='POST':
            assert client.headers['Authorization']=='Bearer independent-key'
            return {'result':f'task-{len(calls)}'}
        return {'status':'SUCCEEDED','model_urls':{'glb':'https://assets.meshy.ai/asset.glb'}}
    def download(client,url,path,cancelled):
        path.write_bytes(asset());return True
    monkeypatch.setattr(cloud3d,'api_request',request)
    monkeypatch.setattr(cloud3d,'download_asset',download)
    body=GenerateRequest(engine='meshy',prompt='兵马俑雕像，高120毫米',reference=picture() if image else None)
    result=cloud3d.generate(body,'a'*32,{'meshy_api_key':'independent-key','meshy_texture':texture},lambda **v:None,lambda:False)
    posts=[r for r in calls if r[0]=='POST']
    assert len(posts)==expected_posts
    assert posts[0][2]['geometry_resolution']=='4k' and posts[0][2]['target_polycount']==200000
    if image:assert posts[0][2]['image_url']==body.reference
    else:assert posts[0][2]['prompt']==body.prompt
    assert result[0]['kind']=='meshy' and result[2]['print_ready']
    saved=(tmp_path/'.runtime/cloud3d'/('a'*32)/'checkpoint.json').read_text('utf-8')
    assert 'independent-key' not in saved
    # A resumed task only polls existing IDs, it does not pay for new creation.
    calls.clear()
    resumed=cloud3d.generate(GenerateRequest(**cloud3d.retry_request('a'*32),resume_job='a'*32),'b'*32,
                           {'meshy_api_key':'independent-key','meshy_texture':texture},lambda **v:None,lambda:False)
    assert not any(r[0]=='POST' for r in calls)
    assert resumed[2]['print_ready']


def test_unconfigured_service_does_not_reuse_language_model_key(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud3d,'ROOT',tmp_path)
    with pytest.raises(ModelingError) as error:
        cloud3d.generate(GenerateRequest(engine='meshy',prompt='完整角色'),'c'*32,{'api_key':'language-key'},lambda **v:None,lambda:False)
    assert error.value.code=='cloud3d_not_configured'


def test_uncertain_creation_checkpoint_does_not_create_another_task(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud3d,'ROOT',tmp_path)
    folder=cloud3d.folder_for('c'*32);folder.mkdir(parents=True)
    cloud3d.save_checkpoint(folder,{'creating':True,'endpoint':'/v2/text-to-3d'})
    def forbidden(*args):pytest.fail('Must not create a second paid task')
    monkeypatch.setattr(cloud3d,'api_request',forbidden)
    with pytest.raises(ModelingError) as error:
        cloud3d.generate(GenerateRequest(engine='meshy',prompt='角色',resume_job='c'*32),'d'*32,{'meshy_api_key':'independent'},lambda **v:None,lambda:False)
    assert error.value.code=='cloud3d_create_uncertain'


def test_source_project_resize_is_local_even_without_service_key(tmp_path,monkeypatch):
    monkeypatch.setattr(cloud3d,'ROOT',tmp_path)
    folder=tmp_path/'data/models'/('a'*32);folder.mkdir(parents=True)
    (folder/'original.glb').write_bytes(asset())
    previous={'kind':'meshy','source_job':'a'*32,'prompt':'角色','params':{'height':120}}
    result=cloud3d.generate(GenerateRequest(prompt='角色',previous=previous,params={'height':180}),'e'*32,{},lambda **v:None,lambda:False)
    assert result[2]['dimensions'][2]==180 and result[0]['source_job']=='e'*32


def test_settings_never_expose_either_service_secret(tmp_path,monkeypatch):
    import server.app as module
    monkeypatch.setattr(module,'DATA',tmp_path)
    (tmp_path/'settings.json').write_text(json.dumps({'enabled':False,'api_key':'text-secret','meshy_api_key':'mesh-secret'}),'utf-8')
    with TestClient(app) as client:
        response=client.get('/api/settings')
        assert 'text-secret' not in response.text and 'mesh-secret' not in response.text
        assert response.json()['has_meshy_key']
        updated=client.put('/api/settings',json={'enabled':False,'clear_meshy_key':True})
        assert not updated.json()['has_meshy_key']


def test_unprintable_asset_can_be_previewed_and_backed_up_but_not_print_exported(tmp_path,monkeypatch):
    import server.app as module
    monkeypatch.setattr(module,'MODELS',tmp_path)
    folder=tmp_path/('a'*32);folder.mkdir()
    (folder/'model.stl').write_bytes(trimesh.creation.box().export(file_type='stl'))
    (folder/'original.glb').write_bytes(asset())
    (folder/'project.json').write_text(json.dumps({'stats':{'print_ready':False}}),'utf-8')
    with TestClient(app) as client:
        for fmt in ['stl','3mf']:
            assert client.get('/api/models/'+('a'*32)+'/download/'+fmt).status_code==422
        assert client.get('/api/models/'+('a'*32)+'/preview.stl').status_code==200
        assert client.get('/api/models/'+('a'*32)+'/download/glb').status_code==200
