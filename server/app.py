from __future__ import annotations

import io
import base64
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from pathlib import Path
from urllib.parse import urlparse
from xml.etree.ElementTree import Element, SubElement, tostring

import httpx
import trimesh
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image

from .modeling import CATALOG, ModelingError, build, plan
from . import neural, blender_bridge, cloud3d, __version__
from .references import normalize_reference

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
MODELS = DATA / "models"
MODELS.mkdir(exist_ok=True)
app = FastAPI(title="小造 Studio", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
jobs: dict = {}
lock = threading.RLock()
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="model")
logger = logging.getLogger("xiaozao")


class GenerateRequest(BaseModel):
    prompt: str = Field(default="", max_length=2000)
    mode: str = "auto"
    params: dict = Field(default_factory=dict)
    previous: dict | None = None
    sketch: list | None = None
    reference: str | None = Field(default=None, max_length=4_000_000)
    engine: str = "parametric"
    steps: int = 32
    seed: int | None = None
    regenerate: bool = False
    detail: Literal["draft", "fine"] = "fine"
    resume_job: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class SettingsRequest(BaseModel):
    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    api_key: str | None = None
    clear_key: bool = False
    meshy_api_key: str | None = None
    clear_meshy_key: bool = False
    meshy_texture: bool = True


class ThumbnailRequest(BaseModel):
    image: str = Field(max_length=700_000)


def settings():
    path = DATA / "settings.json"
    default = {"enabled": False, "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini", "api_key": os.getenv("OPENAI_API_KEY", "")}
    if path.exists():
        try:
            default.update(json.loads(path.read_text("utf-8")))
        except (ValueError, OSError):
            logger.warning("Cannot read settings")
    return default


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "Manifold", "version": __version__}


@app.get("/api/generator")
def generator_status():
    return neural.status()


@app.get("/api/blender")
def blender_status():
    return blender_bridge.status(settings())


@app.get("/api/settings")
def get_settings():
    config = settings()
    return {**{k: v for k, v in config.items() if k not in ("api_key", "meshy_api_key")},
            "has_key": bool(config["api_key"]), "has_meshy_key": bool(config.get("meshy_api_key")),
            "meshy_texture": config.get("meshy_texture", True)}


@app.get("/api/catalog")
def get_catalog():
    return [{"kind": kind, "name": name, "category": category,
             "prompt": f"{words[0]}，高65毫米，带底座" if category == "figurine" else name}
            for kind, (name, category, words) in CATALOG.items() if words]


@app.put("/api/settings")
def save_settings(body: SettingsRequest):
    url = urlparse(body.base_url)
    if url.scheme != "https" and not (url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")):
        raise HTTPException(422, "服务地址需要使用 HTTPS；本机 AI 服务可以使用 HTTP。")
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise HTTPException(422, "请输入不含用户名、密码或查询参数的服务地址。")
    config = settings()
    config.update({"enabled": body.enabled, "base_url": body.base_url.rstrip("/"), "model": body.model.strip()[:100]})
    if body.clear_key:
        config["api_key"] = ""
    elif body.api_key:
        config["api_key"] = body.api_key.strip()
    if body.clear_meshy_key:
        config["meshy_api_key"] = ""
    elif body.meshy_api_key:
        config["meshy_api_key"] = body.meshy_api_key.strip()
    config["meshy_texture"] = body.meshy_texture
    if config["enabled"] and (not config["model"] or (not config["api_key"] and url.hostname not in ("localhost", "127.0.0.1", "::1"))):
        raise HTTPException(422, "开启云端 AI 前，请填写模型名称和 API 密钥。")
    target = DATA / "settings.json"
    target.write_text(json.dumps(config, ensure_ascii=False), "utf-8")
    return get_settings()


def ai_plan(body: GenerateRequest):
    config = settings()
    system = """You design single connected watertight 3D printable solids from a user description. Return ONLY a JSON object {\"name\":\"short Chinese name\",\"scene\":[...],\"height\":60}. Maximum 32 ordered primitives, boolean union or subtraction. Each primitive: {\"shape\":\"box|sphere|cylinder|cone\",\"size\":[x,y,z],\"position\":[x,y,z],\"rotation\":[rx,ry,rz],\"operation\":\"add|subtract\"}. Millimeters, Z up, facing -Y. Shapes are centered on X/Y, start at Z=0 BEFORE rotation and translation. Sphere size is full diameters. Cylinder diameter=size[0], height=size[2]. Cone bottom diameter=size[0], top diameter=size[1], height=size[2]. Union parts must OVERLAP by at least 1mm so it is one connected printable part. Put flat feet or a base at Z=0. Eyes should be subtractive recesses. Subtractions must not split the object. Start with an add. Sizes 0.5..250, coordinates -250..250, target total height 5..250. Do not promise threads, exact topology, mechanical loads or intricate sculptural details. Honor stated dimensions. For unsupported detail use a simplified faithful stylization. Never return code, markdown or explanations."""
    messages = [{"role": "system", "content": system}]
    if body.previous:
        messages.append({"role": "user", "content": "Previous model to modify: " + json.dumps(body.previous, ensure_ascii=False)[:18000]})
    messages.append({"role": "user", "content": body.prompt})
    try:
        response = httpx.post(config["base_url"] + "/chat/completions", headers={"Authorization": "Bearer " + (config["api_key"] or "local")}, json={"model": config["model"], "messages": messages, "temperature": .25, "response_format": {"type": "json_object"}}, timeout=75)
        if response.status_code in (401, 403):
            raise ModelingError("AI 服务拒绝了密钥，请在设置中检查密钥和模型权限。")
        if response.status_code == 429:
            raise ModelingError("AI 服务当前额度不足或请求过多。可以稍后重试，或关闭 AI 使用本地建模。")
        if not response.is_success:
            raise ModelingError(f"AI 服务返回 {response.status_code}，请检查服务地址、模型名称及 JSON 输出支持。")
        content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(content.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
        recipe = {"kind": "custom", "category": "custom", "name": str(result.get("name", "AI 组合模型"))[:40], "scene": result["scene"], "params": {"height": result.get("height", 60)}, "prompt": body.previous.get("prompt", body.prompt) if body.previous else body.prompt, "edits": [*body.previous.get("edits", [])[-29:], body.prompt] if body.previous else []}
        recipe["params"].update({k: v for k, v in body.params.items() if k == "height"})
        return recipe
    except httpx.TimeoutException:
        raise ModelingError("AI 服务响应超时。请稍后重试，或使用本地建模。") from None
    except httpx.RequestError:
        raise ModelingError("连接不到 AI 服务，请检查地址和网络连接。") from None
    except ModelingError:
        raise
    except (KeyError, ValueError, TypeError):
        raise ModelingError("AI 没有返回有效的组合形状。请简化描述后再试。") from None


def update_job(job_id, **values):
    with lock:
        if jobs[job_id]["status"] != "cancelled":
            jobs[job_id].update(values)
            return True
    return False


def cancelled(job_id):
    with lock:
        return jobs[job_id]["status"] == "cancelled"


def run_job(job_id, body):
    target = MODELS / job_id
    try:
        if not update_job(job_id, status="running", progress=15, stage="理解描述与尺寸"):
            return
        config = settings()
        is_blender = body.engine == "blender" or (body.previous or {}).get("kind") == "blender"
        is_neural = body.engine == "neural" or (body.previous or {}).get("kind") == "neural"
        is_cloud = body.engine == "meshy" or (body.previous or {}).get("kind") == "meshy"
        blend_path = script_path = None
        if is_cloud:
            result = cloud3d.generate(body, job_id, config, lambda **v: update_job(job_id, **v), lambda: cancelled(job_id))
            if result is None:
                return
            recipe, mesh, stats, asset = result
        elif is_blender:
            result = blender_bridge.generate(body, job_id, config, lambda **v: update_job(job_id, **v), lambda: cancelled(job_id))
            if result is None:
                return
            recipe, mesh, stats, blend_path, script_path = result
        elif is_neural:
            previous = body.previous or {}
            if previous.get("kind") == "neural" and body.prompt == previous.get("prompt") and not body.regenerate:
                recipe, mesh, stats = neural.restore(previous, body.params)
            else:
                result = neural.generate(body, job_id, lambda **v: update_job(job_id, **v), lambda: cancelled(job_id))
                if result is None:
                    return
                recipe, mesh, stats = result
        elif body.engine == "csg" and config["enabled"] and not body.sketch and (not body.previous or body.prompt != body.previous.get("prompt")):
            recipe = ai_plan(body)
        else:
            recipe = plan(body.prompt, body.mode, body.params, body.previous, body.sketch)
        if not update_job(job_id, progress=95 if is_neural or is_blender or is_cloud else 40, stage="保存模型与工程" if is_neural or is_blender or is_cloud else "构建封闭实体"):
            return
        if not is_neural and not is_blender and not is_cloud:
            mesh, stats = build(recipe)
        if not update_job(job_id, progress=97 if is_neural or is_blender or is_cloud else 80, stage="检查模型与打印文件"):
            return
        target.mkdir(exist_ok=True)
        mesh.export(target / "model.stl")
        if is_cloud:
            shutil.copy2(asset, target / 'original.glb')
        if blend_path and script_path:
            shutil.copy2(blend_path, target / "model.blend")
            shutil.copy2(script_path, target / "model.py")
        meta = {"id": job_id, "name": recipe["name"], "created_at": time.time(), "recipe": recipe, "stats": stats}
        (target / "project.json").write_text(json.dumps(meta, ensure_ascii=False), "utf-8")
        if not update_job(job_id, status="complete", progress=100, stage="模型已就绪", model=meta):
            for file in target.iterdir():
                file.unlink()
            target.rmdir()
    except ModelingError as exc:
        update_job(job_id, status="error", error=str(exc), error_code=exc.code)
    except Exception:
        logger.exception("Model generation failed: %s", job_id)
        update_job(job_id, status="error", error="模型生成没有完成。请简化形状或调整参数，然后重试。")


@app.post("/api/generate", status_code=202)
def generate(body: GenerateRequest):
    if body.resume_job:
        with lock:
            original = jobs.get(body.resume_job)
            if original and original["status"] in ("queued", "running"):
                raise HTTPException(409, "原任务仍在进行，请等待完成或先停止。")
        try:
            saved = cloud3d.retry_request(body.resume_job) if (ROOT / '.runtime' / 'cloud3d' / body.resume_job / 'request.json').is_file() else blender_bridge.retry_request(body.resume_job)
            body = GenerateRequest(**{**saved, "resume_job": body.resume_job})
        except ModelingError as error:
            raise HTTPException(422, str(error)) from None
    if body.engine not in ("blender", "neural", "parametric", "csg", "meshy") or body.steps not in (16, 32, 64):
        raise HTTPException(422, "请选择有效的创作方式和生成质量。")
    if body.seed is not None and not 0 <= body.seed < 2**32:
        raise HTTPException(422, "生成种子需要在 0–4294967295 之间。")
    if body.mode not in ("auto", "figurine", "part", "sketch"):
        raise HTTPException(422, "请选择有效的建模模式。")
    if not body.prompt.strip() and not body.sketch and not body.previous and not body.reference:
        raise HTTPException(422, "先写下想法，或画一个封闭轮廓。")
    if body.reference:
        try:
            body.reference = normalize_reference(body.reference)
        except ModelingError as error:
            raise HTTPException(422, str(error)) from None
    if body.engine == 'meshy' and not body.previous and not body.resume_job:
        if not settings().get('meshy_api_key'):
            raise HTTPException(422, '专业形象生成需要在设置中填写独立的 Meshy API 密钥；当前大模型密钥不能替代。')
        if not body.reference and not body.sketch and len(body.prompt) > 800:
            raise HTTPException(422, '专业形象生成的文字描述请控制在800字以内。')
    if body.sketch and (len(body.sketch) > 16 or any(not isinstance(path, list) or len(path) > 3000 for path in body.sketch)):
        raise HTTPException(422, "草图过于复杂，请简化轮廓。")
    if len(json.dumps(body.model_dump())) > 10_000_000:
        raise HTTPException(422, "项目数据过大，请简化后重试。")
    with lock:
        is_neural = body.engine == "neural" or (body.previous or {}).get("kind") == "neural"
        is_blender = body.engine == "blender" or (body.previous or {}).get("kind") == "blender"
        is_cloud = body.engine == 'meshy' or (body.previous or {}).get('kind') == 'meshy'
        if (is_neural or is_blender or is_cloud) and any(j["status"] in ("queued", "running") and j.get("engine") in ("neural", "blender", "meshy") for j in jobs.values()):
            raise HTTPException(429, "已有自由模型正在生成。这台电脑每次生成一个，完成或停止后可以继续。")
        if sum(j["status"] in ("queued", "running") for j in jobs.values()) >= 4:
            raise HTTPException(429, "已有模型正在生成，请等待完成后再试。")
        # Keep terminal job records bounded in long-running desktop sessions.
        for key in list(jobs)[:-60]:
            if jobs[key]["status"] not in ("queued", "running"):
                del jobs[key]
        job_id = uuid.uuid4().hex
        jobs[job_id] = {"id": job_id, "status": "queued", "progress": 5, "stage": "准备建模", "engine": "meshy" if is_cloud else "blender" if is_blender else "neural" if is_neural else "parametric", "created_at": time.time()}
    pool.submit(run_job, job_id, body)
    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with lock:
        if job_id not in jobs:
            raise HTTPException(404, "任务不存在，服务可能已经重启。请重新生成。")
        return dict(jobs[job_id])


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str):
    with lock:
        if job_id not in jobs:
            raise HTTPException(404, "任务不存在。")
        if jobs[job_id]["status"] in ("queued", "running"):
            jobs[job_id]["status"] = "cancelled"
        return dict(jobs[job_id])


def model_folder(model_id: str):
    if len(model_id) != 32 or any(c not in "0123456789abcdef" for c in model_id):
        raise HTTPException(404, "找不到这个模型。")
    folder = MODELS / model_id
    if not (folder / "project.json").exists():
        raise HTTPException(404, "找不到这个模型，可能已经被删除。")
    return folder


@app.get("/api/models")
def list_models():
    found = []
    for file in MODELS.glob("*/project.json"):
        try:
            item = json.loads(file.read_text("utf-8"))
            item["thumbnail"] = (file.parent / "thumbnail.png").exists()
            found.append(item)
        except (OSError, ValueError):
            pass
    return sorted(found, key=lambda x: x["created_at"], reverse=True)[:100]


@app.get("/api/models/{model_id}")
def get_model(model_id: str):
    folder = model_folder(model_id)
    return {**json.loads((folder / "project.json").read_text("utf-8")), "thumbnail": (folder / "thumbnail.png").exists()}


@app.post("/api/models/{model_id}/thumbnail")
def save_thumbnail(model_id: str, body: ThumbnailRequest):
    folder = model_folder(model_id)
    if (folder / "thumbnail.png").exists():
        return {"ok": True}
    try:
        data = base64.b64decode(body.image.split(",", 1)[-1], validate=True)
        with Image.open(io.BytesIO(data)) as img:
            if img.width > 640 or img.height > 640:
                raise ValueError("Too large")
            img.convert("RGBA").save(folder / "thumbnail.png", "PNG")
    except Exception:
        raise HTTPException(422, "预览缩略图无效。") from None
    return {"ok": True}


@app.get("/api/models/{model_id}/thumbnail")
def get_thumbnail(model_id: str):
    path = model_folder(model_id) / "thumbnail.png"
    if not path.exists():
        raise HTTPException(404, "缩略图尚未生成。")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.delete("/api/models/{model_id}")
def delete_model(model_id: str):
    folder = model_folder(model_id)
    for file in folder.iterdir():
        if file.is_file():
            file.unlink()
    folder.rmdir()
    return {"ok": True}


def export_3mf(mesh):
    ns = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    root = Element("model", {"unit": "millimeter", "xmlns": ns, "xml:lang": "zh-CN"})
    resources = SubElement(root, "resources")
    obj = SubElement(resources, "object", {"id": "1", "type": "model", "name": "Xiaozao model"})
    node = SubElement(obj, "mesh")
    vertices = SubElement(node, "vertices")
    for x, y, z in mesh.vertices:
        # Preserve intersections already validated in the STL representation.
        # Six fixed decimal places can merge nearby relief vertices and open
        # an otherwise closed mesh when a slicer welds duplicate positions.
        SubElement(vertices, "vertex", {"x": repr(float(x)), "y": repr(float(y)), "z": repr(float(z))})
    triangles = SubElement(node, "triangles")
    for a, b, c in mesh.faces:
        SubElement(triangles, "triangle", {"v1": str(a), "v2": str(b), "v3": str(c)})
    SubElement(SubElement(root, "build"), "item", {"objectid": "1"})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        archive.writestr("3D/3dmodel.model", tostring(root, encoding="utf-8", xml_declaration=True))
    return stream.getvalue()


@app.get("/api/models/{model_id}/download/{fmt}")
def download(model_id: str, fmt: str):
    folder = model_folder(model_id)
    metadata = json.loads((folder / 'project.json').read_text('utf-8'))
    if fmt in ('stl', '3mf') and metadata['stats'].get('print_ready') is False:
        raise HTTPException(422, '原始形象已保留，但尚未通过打印检查。请先在 Blender 中修复实体连接和开放表面。')
    if fmt == 'glb':
        if not (folder / 'original.glb').is_file():
            raise HTTPException(404, '这件作品没有原始GLB文件。')
        return FileResponse(folder / 'original.glb', filename=f'xiaozao-{model_id[:6]}-original.glb', media_type='model/gltf-binary')
    if fmt == "json":
        return FileResponse(folder / "project.json", filename=f"xiaozao-{model_id[:6]}.json", media_type="application/json")
    if fmt == "stl":
        return FileResponse(folder / "model.stl", filename=f"xiaozao-{model_id[:6]}-mm.stl", media_type="model/stl")
    if fmt in ("blend", "py"):
        path = folder / ("model." + fmt)
        if not path.is_file():
            raise HTTPException(404, "这件作品没有 Blender 工程。请使用「AI + Blender」创作。")
        return FileResponse(path, filename=f"xiaozao-{model_id[:6]}.{fmt}", media_type="application/octet-stream" if fmt == "blend" else "text/plain; charset=utf-8")
    if fmt not in ("obj", "3mf"):
        raise HTTPException(400, "支持 STL、3MF、OBJ 或项目 JSON。")
    mesh = trimesh.load(folder / "model.stl", force="mesh")
    result = export_3mf(mesh) if fmt == "3mf" else mesh.export(file_type="obj").encode("utf-8")
    return Response(result, media_type="model/3mf" if fmt == "3mf" else "text/plain", headers={"Content-Disposition": f'attachment; filename="xiaozao-{model_id[:6]}-mm.{fmt}"'})


@app.get('/api/models/{model_id}/preview.stl')
def preview_mesh(model_id: str):
    return FileResponse(model_folder(model_id) / 'model.stl', media_type='model/stl')


@app.post("/api/models/{model_id}/open-blender")
def open_in_blender(model_id: str):
    path = model_folder(model_id) / "model.blend"
    if not path.is_file():
        raise HTTPException(404, "这件作品没有 Blender 工程。")
    executable = blender_bridge.find_blender()
    if executable is None:
        raise HTTPException(422, "没有找到本机 Blender，请先安装。")
    subprocess.Popen([str(executable), "--disable-autoexec", str(path)], cwd=path.parent)
    return {"ok": True}


# Serve the compiled app on the same origin; development uses Vite's proxy.
if (ROOT / "dist").exists():
    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="frontend")
