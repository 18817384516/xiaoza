"""Local generative model orchestration and printable mesh normalization."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import manifold3d as manifold
import numpy as np
import trimesh

from .modeling import ModelingError, number

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "ai_models"
CHECKPOINTS = ["text_cond.pt", "vector_decoder.pt", "ViT-L-14.pt", "text_cond_config.yaml", "vector_decoder_config.yaml", "diffusion_config.yaml"]
TRANSLATION = ["config.json", "pytorch_model.bin", "source.spm", "target.spm", "vocab.json", "tokenizer_config.json"]


def status():
    missing = [name for name in CHECKPOINTS if not (CACHE / name).is_file()]
    missing += ["translation/" + name for name in TRANSLATION if not (CACHE / "translation" / name).is_file()]
    dependencies = [name for name in ("torch", "torchvision", "transformers", "yaml", "blobfile", "ftfy") if importlib.util.find_spec(name) is None]
    return {"ready": not missing and not dependencies, "missing_files": missing, "missing_dependencies": dependencies,
            "name": "Shap-E", "device": "CPU", "local": True}


def encode_mesh(mesh):
    stream = io.BytesIO()
    np.savez_compressed(stream, vertices=np.asarray(mesh.vertices, dtype=np.float32), faces=np.asarray(mesh.faces, dtype=np.int32))
    return base64.b64encode(stream.getvalue()).decode("ascii")


def decode_mesh(encoded):
    try:
        if not isinstance(encoded, str) or len(encoded) > 8_000_000:
            raise ValueError("Mesh payload too large")
        stream = io.BytesIO(base64.b64decode(encoded, validate=True))
        with zipfile.ZipFile(stream) as archive:
            if len(archive.infolist()) != 2 or sum(item.file_size for item in archive.infolist()) > 32_000_000:
                raise ValueError("Invalid mesh archive")
        stream.seek(0)
        with np.load(stream, allow_pickle=False) as data:
            vertices, faces = data["vertices"], data["faces"]
            if vertices.ndim != 2 or faces.ndim != 2 or vertices.shape[1] != 3 or faces.shape[1] != 3:
                raise ValueError("Invalid mesh array dimensions")
            if not 4 <= len(vertices) <= 200_000 or not 4 <= len(faces) <= 400_000:
                raise ValueError("Invalid mesh size")
            if not np.issubdtype(vertices.dtype, np.number) or not np.isfinite(vertices).all():
                raise ValueError("Invalid coordinates")
            if not np.issubdtype(faces.dtype, np.integer) or faces.min() < 0 or faces.max() >= len(vertices):
                raise ValueError("Invalid indices")
            return trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, TypeError):
        raise ModelingError("项目中的生成网格无效，请重新选择完整的小造项目。") from None


def finish_mesh(mesh, height=65, base=True):
    if not isinstance(height, (int, float)) or not math.isfinite(height) or not 5 <= height <= 250:
        raise ModelingError("模型高度需要在 5–250 毫米之间。")
    if not isinstance(base, bool):
        raise ModelingError("底座开关需要是开启或关闭。")
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals(multibody=True)
    pieces = [piece for piece in mesh.split(only_watertight=False) if len(piece.faces) >= 4]
    if not pieces:
        raise ModelingError("这次没有形成有效表面，请换个描述或再生成一版。")
    pieces.sort(key=lambda part: abs(part.volume), reverse=True)
    mesh = pieces[0]
    removed = len(pieces) - 1
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
    if mesh.volume < 0:
        mesh.invert()
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        raise ModelingError("生成的表面未通过封闭性检查，请再生成一版；没有替换成预设模型。")
    if mesh.extents[2] <= 1e-8:
        raise ModelingError("生成的形状过于扁平，请换个描述重试。")
    base_height = 2.0 if base else 0
    mesh.apply_scale((height - base_height) / mesh.extents[2])
    mesh.apply_translation([-mesh.bounds[:, 0].mean(), -mesh.bounds[:, 1].mean(), -mesh.bounds[0, 2] + base_height - (0.6 if base else 0)])
    if base:
        # The plate overlaps the lowest material, so the result remains one solid.
        solid = manifold.Manifold(manifold.Mesh(np.asarray(mesh.vertices, dtype=np.float32), np.asarray(mesh.faces, dtype=np.uint32)))
        w, d = mesh.extents[:2] + 4
        plate = manifold.Manifold.cube((float(w), float(d), base_height)).translate((-w / 2, -d / 2, 0))
        solid = solid + plate
        if solid.status() != manifold.Error.NoError or solid.is_empty():
            raise ModelingError("这次生成的表面无法添加底座，请关闭底座或再生成一版。")
        raw = solid.to_mesh()
        mesh = trimesh.Trimesh(np.asarray(raw.vert_properties)[:, :3], np.asarray(raw.tri_verts), process=True)
        mesh.apply_scale(height / mesh.extents[2])
    mesh.apply_translation([0, 0, -mesh.bounds[0, 2]])
    components = sum(part.volume > 1e-7 for part in mesh.split(only_watertight=False))
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0 or components != 1:
        raise ModelingError("网格尚未形成一个封闭实体，请再生成一版。")
    warnings = ["这是 AI 新生成的近似造型，细节和尺寸关系需要预览确认；不代表已验证壁厚、装配或承载。"]
    if removed:
        warnings.append(f"已移除 {removed} 个分离的表面片，只保留主要实体；请检查是否缺少预期部件。")
    if not base:
        warnings.append("未加底座，请在切片软件中确认底面、摆放和支撑。")
    return mesh, {"dimensions": [round(float(value), 2) for value in mesh.extents],
                  "volume_cm3": round(float(mesh.volume) / 1000, 3), "triangles": len(mesh.faces),
                  "watertight": True, "components": 1, "warnings": warnings, "units": "mm"}


def restore(recipe, params):
    settings = {**recipe.get("params", {}), **{k: v for k, v in params.items() if k in ("height", "base")}}
    raw = decode_mesh(recipe.get("mesh"))
    mesh, stats = finish_mesh(raw, settings.get("height", 65), settings.get("base", True))
    return {**recipe, "params": settings}, mesh, stats


def generate(body, job_id, update, cancelled):
    engine = status()
    if not engine["ready"]:
        raise ModelingError("本地自由生成模型尚未准备完整，请运行「安装自由生成.cmd」完成下载后重试。", code="generator_not_ready")
    folder = ROOT / ".runtime" / "neural" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    prompt = body.prompt.strip()
    previous = body.previous or {}
    if previous.get("kind") == "neural" and prompt != previous.get("prompt"):
        original = previous.get("generation_prompt", previous.get("prompt", ""))
        prompt = original + "；修改要求：" + prompt
    height = body.params.get("height", number(prompt.lower(), ["总高", "高度", "高", "height"]) or previous.get("params", {}).get("height", 65))
    base = body.params.get("base", previous.get("params", {}).get("base", True))
    if "不要底座" in prompt or "去掉底座" in prompt:
        base = False
    request = {"prompt": prompt, "seed": body.seed if body.seed is not None else int.from_bytes(os.urandom(4), "little"),
               "steps": body.steps, "sketch": body.sketch}
    (folder / "request.json").write_text(json.dumps(request, ensure_ascii=False), "utf-8")
    started = time.monotonic()
    for phase in ("translate", "condition", "sample", "decode"):
        if cancelled():
            return None
        with (folder / (phase + ".log")).open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, "-m", "server.neural_worker", phase, str(folder)],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                while process.poll() is None:
                    if cancelled():
                        process.terminate()
                        process.wait(timeout=15)
                        return None
                    try:
                        current = json.loads((folder / "progress.json").read_text("utf-8"))
                        current.pop("failure", None)
                        update(**current, elapsed_seconds=round(time.monotonic() - started))
                    except (OSError, ValueError):
                        pass
                    time.sleep(.5)
                if process.returncode:
                    raise ModelingError(f"本地自由生成在「{ {'translate':'理解中文','condition':'编码描述','sample':'创造形状','decode':'提取表面'}[phase] }」阶段未完成。详细记录保存在 .runtime/neural；可以重试。", code="neural_failure")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=15)
    if cancelled():
        return None
    with np.load(folder / "raw_mesh.npz", allow_pickle=False) as data:
        raw = trimesh.Trimesh(data["vertices"], data["faces"], process=True)
    mesh, stats = finish_mesh(raw, height, base)
    recipe = {"kind": "neural", "category": "generative", "name": (body.prompt.split("，")[0] or "自由生成作品")[:30],
              "params": {"height": height, "base": base}, "prompt": previous.get("prompt", body.prompt) if previous else body.prompt,
              "generation_prompt": prompt, "translated_prompt": (folder / "english.txt").read_text("utf-8"),
              "seed": request["seed"], "steps": body.steps, "generator": "Shap-E", "mesh": encode_mesh(raw),
              "edits": [*previous.get("edits", [])[-29:], body.prompt] if previous else []}
    if body.sketch:
        recipe["sketch"] = body.sketch
        stats["warnings"].append("草图作为较弱的外形参考与文字共同参与；没有强制轮廓或精确重建。")
    stats["generation_seconds"] = round(time.monotonic() - started, 1)
    return recipe, mesh, stats
