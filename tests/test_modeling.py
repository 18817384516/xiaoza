import io
import json
import math
import time
import zipfile
import base64
from xml.etree import ElementTree as ET

import numpy as np
import pytest
import trimesh
from PIL import Image
from fastapi.testclient import TestClient

from server.modeling import CATALOG, ModelingError, build, plan
import server.app as backend


@pytest.mark.parametrize("kind", [k for k in CATALOG if k not in ("sketch", "custom")])
def test_every_template_is_one_positive_watertight_solid(kind):
    recipe = plan(CATALOG[kind][2][0])
    assert recipe["kind"] == kind
    mesh, stats = build(recipe)
    assert mesh.is_watertight and mesh.is_winding_consistent
    assert mesh.volume > 0
    assert stats["components"] == 1
    assert np.isclose(mesh.bounds[0, 2], 0)
    assert np.isfinite(mesh.vertices).all()


def test_language_dimensions_units_and_hole_independence():
    p = plan("安装板，长8厘米宽4厘米厚5毫米，4个孔，孔直径5毫米")["params"]
    assert p["width"] == 80 and p["depth"] == 40 and p["height"] == 5 and p["hole_diameter"] == 5
    assert plan("小兔，6厘米高")["params"]["height"] == 60
    p = plan("收纳盒 80 x 60 x 30 mm，壁厚2.4毫米")["params"]
    assert (p["width"], p["depth"], p["height"]) == (80, 60, 30)
    assert plan("安装板，两个孔")["params"]["holes"] == 2


def test_plate_and_washer_real_holes_and_exact_dimensions():
    mesh, _ = build(plan("安装板，长80宽40厚5，4个孔，孔径5，公差0"))
    assert np.allclose(mesh.extents, [80, 40, 5], atol=.001)
    assert mesh.volume == pytest.approx(80 * 40 * 5 - 4 * math.pi * 2.5**2 * 5, rel=.001)
    mesh, _ = build(plan("垫片，外径24厚3内径8，公差0"))
    assert mesh.volume == pytest.approx(math.pi * (12**2 - 4**2) * 3, rel=.002)


def test_continuation_keeps_parameters_and_changes_shape():
    first = plan("小兔，高70毫米")
    second = plan("耳朵大一点", previous=first)
    assert second["kind"] == "bunny" and second["params"]["height"] == 70
    assert second["params"]["ear_scale"] > first["params"]["ear_scale"]
    assert second["prompt"] == first["prompt"]
    assert second["edits"] == ["耳朵大一点"]
    mesh1, _ = build(first)
    mesh2, _ = build(second)
    assert not math.isclose(mesh1.volume, mesh2.volume)


def test_sketch_hole_survives_extrusion():
    paths = [[[0, 0], [100, 0], [100, 100], [0, 100]], [[25, 25], [75, 25], [75, 75], [25, 75]]]
    mesh, stats = build(plan("", overrides={"width": 60, "height": 8}, sketch=paths))
    assert np.allclose(mesh.extents, [60, 60, 8])
    assert mesh.volume == pytest.approx((60**2 - 30**2) * 8)
    assert stats["watertight"]


def test_disconnected_sketch_rejected():
    with pytest.raises(ModelingError, match="分离"):
        build(plan("", sketch=[[[0, 0], [10, 0], [10, 10], [0, 10]], [[20, 20], [30, 20], [30, 30], [20, 30]]]))


@pytest.mark.parametrize("prompt", ["支架，孔径30", "收纳盒，壁厚20", "小兔，高0毫米", "小兔，高-5毫米", "垫片，内径24", "齿轮，齿数7", "安装板，3个孔"])
def test_invalid_dimensions_fail_with_actionable_message(prompt):
    with pytest.raises(ModelingError):
        plan(prompt)


def test_unknown_prompt_does_not_fabricate_an_unrelated_model():
    with pytest.raises(ModelingError, match="本地") as error:
        plan("复杂的喷气式飞机发动机")
    assert error.value.code == "unsupported_description"


def test_direction_preference_does_not_reject_a_supported_description():
    assert plan("一只小兔，高70毫米", mode="part")["kind"] == "bunny"
    assert plan("安装板，长80宽40厚5", mode="figurine")["kind"] == "plate"


def test_english_words_do_not_accidentally_match_template_substrings():
    for prompt in ("a complicated engine", "a doghouse", "a gearbox"):
        with pytest.raises(ModelingError):
            plan(prompt)
    assert plan("a CAT, height 60 mm")["kind"] == "cat"


def test_catalog_examples_match_their_actual_local_model(client):
    items = client.get("/api/catalog").json()
    assert len(items) == len([v for v in CATALOG.values() if v[2]])
    for item in items:
        assert plan(item["prompt"])["kind"] == item["kind"]


def test_custom_csg_and_disconnected_parts():
    recipe = {"kind": "custom", "category": "custom", "params": {"height": 20}, "scene": [{"shape": "box", "size": [40, 40, 20]}, {"shape": "cylinder", "size": [10, 10, 24], "position": [0, 0, -2], "operation": "subtract"}]}
    mesh, _ = build(recipe)
    assert mesh.volume < 40 * 40 * 20
    recipe["scene"] = [{"shape": "box", "size": [10, 10, 10]}, {"shape": "sphere", "size": [10, 10, 10], "position": [50, 50, 50]}]
    with pytest.raises(ModelingError, match="分离"):
        build(recipe)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, "DATA", tmp_path)
    monkeypatch.setattr(backend, "MODELS", tmp_path / "models")
    backend.MODELS.mkdir()
    return TestClient(backend.app)


def wait_job(client, id):
    for _ in range(200):
        result = client.get("/api/jobs/" + id).json()
        if result["status"] in ("complete", "error", "cancelled"):
            return result
        time.sleep(.025)
    pytest.fail("Job did not finish")


def test_connection_retry_restores_server_saved_request_instead_of_browser_prompt(client,monkeypatch):
    monkeypatch.setattr(backend.blender_bridge,'retry_request',lambda identifier:{'prompt':'原始瑞兽描述','engine':'blender','params':{'height':76}})
    captured=[]
    def inspect(body,*args,**kwargs):
        captured.append(body)
        raise ModelingError('测试保存的请求',code='test_inspected')
    monkeypatch.setattr(backend.blender_bridge,'generate',inspect)
    response=client.post('/api/generate',json={'prompt':'不应覆盖原始描述','resume_job':'f'*32})
    assert response.status_code==202
    job=wait_job(client,response.json()['id'])
    assert job['error_code']=='test_inspected'
    assert captured[0].prompt=='原始瑞兽描述' and captured[0].params['height']==76
    assert captured[0].resume_job=='f'*32
    assert client.post('/api/generate',json={'prompt':'','resume_job':'../settings'}).status_code==422


def test_end_to_end_api_export_reload_and_history(client):
    response = client.post("/api/generate", json={"prompt": "安装板，长80宽40厚5，孔径5"})
    assert response.status_code == 202
    result = wait_job(client, response.json()["id"])
    assert result["status"] == "complete", result
    model = result["model"]
    id = model["id"]
    stl = client.get(f"/api/models/{id}/download/stl")
    assert stl.status_code == 200
    mesh = trimesh.load(io.BytesIO(stl.content), file_type="stl")
    assert mesh.is_watertight and np.allclose(mesh.extents, [80, 40, 5])
    three = client.get(f"/api/models/{id}/download/3mf")
    assert three.status_code == 200
    with zipfile.ZipFile(io.BytesIO(three.content)) as archive:
        root = ET.fromstring(archive.read("3D/3dmodel.model"))
        assert root.attrib["unit"] == "millimeter"
    loaded = trimesh.load(io.BytesIO(three.content), file_type="3mf").to_mesh()
    assert loaded.is_watertight and np.allclose(loaded.extents, mesh.extents)
    obj = client.get(f"/api/models/{id}/download/obj")
    loaded_obj = trimesh.load(io.BytesIO(obj.content), file_type="obj")
    assert loaded_obj.is_watertight
    project = client.get(f"/api/models/{id}/download/json").json()
    assert project["recipe"]["params"]["width"] == 80
    image = Image.new("RGBA", (320, 260), "purple")
    image_stream = io.BytesIO()
    image.save(image_stream, format="PNG")
    encoded = "data:image/png;base64," + base64.b64encode(image_stream.getvalue()).decode()
    assert client.post(f"/api/models/{id}/thumbnail", json={"image": encoded}).status_code == 200
    assert client.get(f"/api/models/{id}/thumbnail").headers["content-type"] == "image/png"
    assert client.get(f"/api/models/{id}").json()["thumbnail"] is True
    assert client.get("/api/models").json()[0]["id"] == id
    assert client.delete(f"/api/models/{id}").status_code == 200
    assert client.get("/api/models").json() == []
    assert client.get(f"/api/models/{id}/download/stl").status_code == 404


def test_errors_settings_key_redaction_and_path_validation(client):
    assert client.post("/api/generate", json={"prompt": ""}).status_code == 422
    result = client.post("/api/generate", json={"prompt": "任意不支持的设备"}).json()
    failed = wait_job(client, result["id"])
    assert failed["status"] == "error"
    assert failed["error_code"] == "unsupported_description"
    assert client.get("/api/models/invalid/download/stl").status_code == 404
    response = client.put("/api/settings", json={"enabled": True, "api_key": "test-secret", "base_url": "https://example.com/v1", "model": "test"})
    assert response.status_code == 200
    assert "test-secret" not in response.text
    assert response.json()["has_key"]
    assert "test-secret" not in client.get("/api/settings").text
    assert client.put("/api/settings", json={"enabled": True, "clear_key": True}).status_code == 422
    assert client.put("/api/settings", json={"enabled": False, "clear_key": True}).json()["has_key"] is False
    assert client.put("/api/settings", json={"base_url": "http://example.com/v1"}).status_code == 422


def test_cancel_queued_ai_job_does_not_publish_model(client, monkeypatch):
    def slow_plan(body):
        time.sleep(.2)
        return plan("小兔")
    monkeypatch.setattr(backend, "settings", lambda: {"enabled": True})
    monkeypatch.setattr(backend, "ai_plan", slow_plan)
    id = client.post("/api/generate", json={"prompt": "小兔", "engine": "csg"}).json()["id"]
    assert client.delete("/api/jobs/" + id).json()["status"] == "cancelled"
    time.sleep(.3)
    assert client.get("/api/models").json() == []


def test_ai_protocol_to_real_boolean_mesh_without_executing_code(client, monkeypatch):
    scene = [{"shape": "box", "size": [40, 40, 20]}, {"shape": "cylinder", "size": [10, 10, 24], "position": [0, 0, -2], "operation": "subtract"}]
    def mock_post(url, **kwargs):
        assert url == "https://example.com/v1/chat/completions"
        assert kwargs["json"]["response_format"]["type"] == "json_object"
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        return backend.httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"name": "组合测试", "height": 20, "scene": scene})}}]})
    monkeypatch.setattr(backend.httpx, "post", mock_post)
    client.put("/api/settings", json={"enabled": True, "base_url": "https://example.com/v1", "model": "test-model", "api_key": "test-key"})
    id = client.post("/api/generate", json={"prompt": "带圆孔的方块", "engine": "csg"}).json()["id"]
    result = wait_job(client, id)
    assert result["status"] == "complete", result
    assert result["model"]["recipe"]["kind"] == "custom"
    assert result["model"]["stats"]["watertight"]
    assert np.allclose(result["model"]["stats"]["dimensions"], [40, 40, 20])


def test_ai_failure_is_specific_and_never_fakes_a_model(client, monkeypatch):
    monkeypatch.setattr(backend.httpx, "post", lambda *a, **k: backend.httpx.Response(401))
    client.put("/api/settings", json={"enabled": True, "base_url": "https://example.com/v1", "model": "test", "api_key": "bad-key"})
    id = client.post("/api/generate", json={"prompt": "一个模型", "engine": "csg"}).json()["id"]
    result = wait_job(client, id)
    assert result["status"] == "error" and "密钥" in result["error"]
    assert client.get("/api/models").json() == []
