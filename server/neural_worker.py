"""Isolated CPU stages for actual Shap-E diffusion, never template selection.

Each stage exits to return memory to Windows before the next model loads.
Vendored upstream source and checkpoint licenses live in third_party/.
"""
from __future__ import annotations

import gc
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "third_party" / "shap-e-main"))
sys.path.insert(0, str(ROOT / "third_party" / "CLIP-main"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
CACHE = ROOT / "data" / "ai_models"
WORK: Path


def report(progress, stage, **extra):
    path = WORK / "progress.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"progress": progress, "stage": stage, **extra}, ensure_ascii=False), "utf-8")
    temp.replace(path)
    print(stage, flush=True)


def translate(request):
    prompt = request["prompt"]
    if re.search(r"[\u4e00-\u9fff]", prompt):
        report(8, "在本机理解中文描述")
        from transformers import MarianMTModel, MarianTokenizer
        import torch
        source = str(CACHE / "translation")
        tokenizer = MarianTokenizer.from_pretrained(source, local_files_only=True)
        model = MarianMTModel.from_pretrained(source, local_files_only=True).eval()
        texts = [prompt[i:i + 200] for i in range(0, len(prompt), 200)]
        output = []
        with torch.inference_mode():
            for text in texts:
                tokens = tokenizer(text, return_tensors="pt", truncation=True, max_length=384)
                result = model.generate(**tokens, max_new_tokens=160, num_beams=3)
                output.append(tokenizer.decode(result[0], skip_special_tokens=True))
        english = " ".join(output)
    else:
        english = prompt
    if not english.strip():
        raise ValueError("本地翻译没有产生有效描述，请换一种说法重试。")
    (WORK / "english.txt").write_text(english, "utf-8")
    report(13, "描述已就绪，准备生成全新形状", translated_prompt=english)


def condition(request):
    report(15, "载入本地语义编码模型")
    import torch
    import clip
    model, preprocess = clip.load(str(CACHE / "ViT-L-14.pt"), device="cpu")
    model.eval()
    # Only the text encoder is needed for text generation.
    if not request.get("sketch"):
        del model.visual
        gc.collect()
    with torch.inference_mode():
        english = (WORK / "english.txt").read_text("utf-8")
        tokens = clip.tokenize([english], truncate=True)
        text = model.encode_text(tokens).float()
        text /= torch.linalg.vector_norm(text, dim=-1, keepdim=True)
        if request.get("sketch"):
            from PIL import Image, ImageDraw
            image = Image.new("RGB", (640, 420), "white")
            draw = ImageDraw.Draw(image)
            for path in request["sketch"]:
                points = [(float(x), float(y)) for x, y in path]
                if len(points) > 2:
                    draw.line(points + [points[0]], fill="#333333", width=6, joint="curve")
            image.save(WORK / "sketch-reference.png")
            visual = model.encode_image(preprocess(image).unsqueeze(0)).float()
            visual /= torch.linalg.vector_norm(visual, dim=-1, keepdim=True)
            # CLIP has a shared image/text embedding space. This is a soft reference,
            # not a promise of exact perspective reconstruction or contour fidelity.
            text = 0.85 * text + 0.15 * visual
            text /= torch.linalg.vector_norm(text, dim=-1, keepdim=True)
        torch.save(text, WORK / "conditioning.pt")
    report(22, "语义已编码，准备三维扩散")


def efficient_attention(self, qkv):
    import torch
    batch, length, width = qkv.shape
    channels = width // self.heads // 3
    q, k, v = qkv.view(batch, length, self.heads, -1).split(channels, dim=-1)
    value = torch.nn.functional.scaled_dot_product_attention(
        q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2), dropout_p=0.0)
    return value.transpose(1, 2).reshape(batch, length, -1)


def sample(request):
    report(24, "载入三维扩散模型")
    import torch
    import yaml
    from shap_e.models.generation import transformer
    from shap_e.models.configs import model_from_config
    from shap_e.diffusion.gaussian_diffusion import diffusion_from_config
    from shap_e.diffusion.k_diffusion import karras_sample_progressive

    class PrecomputedCLIP:
        feature_dim = 768
        grid_size = 16
        grid_feature_dim = 1024

        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, batch_size, embeddings=None, **kwargs):
            if embeddings is None:
                raise ValueError("Missing local conditioning")
            return embeddings

    transformer.FrozenImageCLIP = PrecomputedCLIP
    transformer.QKVMultiheadAttention.forward = efficient_attention
    config = yaml.safe_load((CACHE / "text_cond_config.yaml").read_text("utf-8"))
    model = model_from_config(config, device=torch.device("cpu"))
    weights = torch.load(CACHE / "text_cond.pt", map_location="cpu", weights_only=True, mmap=True)
    model.load_state_dict(weights, assign=True)
    model.eval()
    del weights
    gc.collect()
    diffusion = diffusion_from_config(yaml.safe_load((CACHE / "diffusion_config.yaml").read_text("utf-8")))
    embeddings = torch.load(WORK / "conditioning.pt", weights_only=True)
    embeddings = torch.cat([embeddings, torch.zeros_like(embeddings)], dim=0)
    steps = request.get("steps", 32)
    torch.manual_seed(request["seed"])
    started = time.monotonic()
    latent = None
    with torch.inference_mode():
        for index, state in enumerate(karras_sample_progressive(
            diffusion=diffusion, model=model, shape=(1, model.d_latent), steps=steps,
            clip_denoised=True, model_kwargs={"embeddings": embeddings}, device=torch.device("cpu"),
            sigma_min=1e-3, sigma_max=160, s_churn=0, guidance_scale=15, progress=False,
        )):
            latent = state["x"]
            elapsed = time.monotonic() - started
            completed = min(index + 1, steps)
            report(26 + round(45 * completed / steps), f"正在创造三维形状 · {completed}/{steps}",
                   remaining_seconds=max(0, round(elapsed / (index + 1) * (steps - index - 1))))
    if latent is None:
        raise ValueError("本地扩散没有返回形状，请重试。")
    torch.save(latent[0], WORK / "latent.pt")
    report(72, "形状已生成，准备提取表面")


def decode(request):
    report(74, "载入三维表面解码模型")
    import numpy as np
    import torch
    import yaml
    from skimage.measure import marching_cubes
    from shap_e.models.configs import model_from_config
    from shap_e.models.query import Query
    from shap_e.util.collections import AttrDict
    config = yaml.safe_load((CACHE / "vector_decoder_config.yaml").read_text("utf-8"))
    model = model_from_config(config, device=torch.device("cpu"))
    weights = torch.load(CACHE / "vector_decoder.pt", map_location="cpu", weights_only=True, mmap=True)
    model.load_state_dict(weights, assign=True)
    model.eval()
    del weights
    gc.collect()
    resolution = 96 if request.get("steps", 32) < 64 else 128
    axis = torch.linspace(-1, 1, resolution)
    positions = torch.stack(torch.meshgrid(axis, axis, axis, indexing="ij"), dim=-1).reshape(-1, 3)
    values = []
    with torch.inference_mode():
        latent = torch.load(WORK / "latent.pt", weights_only=True)
        params = model.bottleneck_to_params(latent[None])
        for start in range(0, len(positions), 4096):
            batch = positions[start:start + 4096][None]
            field = model.renderer.get_signed_distance(Query(position=batch), params, AttrDict())
            values.append(field.flatten().numpy().copy())
            if start % (4096 * 20) == 0:
                report(77 + round(13 * start / len(positions)), "把生成形状转换为三角网格")
    field = np.concatenate(values).reshape((resolution,) * 3)
    field = np.pad(field, 1, constant_values=-1)
    vertices, faces, _, _ = marching_cubes(field, level=0)
    np.savez_compressed(WORK / "raw_mesh.npz", vertices=vertices, faces=faces)
    report(92, "网格已生成，正在检查打印条件")


def main():
    global WORK
    phase, folder = sys.argv[1:3]
    WORK = Path(folder).resolve()
    request = json.loads((WORK / "request.json").read_text("utf-8"))
    import torch
    torch.set_num_threads(max(1, min(3, (os.cpu_count() or 2) - 1)))
    torch.set_num_interop_threads(1)
    {"translate": translate, "condition": condition, "sample": sample, "decode": decode}[phase](request)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback
        traceback.print_exc()
        report(0, "生成没有完成", failure=str(error)[:500])
        sys.exit(1)
