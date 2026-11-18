"""Download official Shap-E checkpoints, with resume and checksum validation."""
from pathlib import Path
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import time
import sys
import httpx

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "ai_models"
CACHE.mkdir(parents=True, exist_ok=True)


def download(url, destination, expected=None):
    destination = Path(destination)
    if destination.exists() and (not expected or digest(destination) == expected):
        print(f"ready: {destination.name}", flush=True)
        return
    partial = destination.with_suffix(destination.suffix + ".partial")
    for attempt in range(12):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            with httpx.stream("GET", url, headers={"Range": f"bytes={offset}-"} if offset else {},
                              follow_redirects=True, timeout=120) as response:
                response.raise_for_status()
                resume = offset and response.status_code == 206
                with partial.open("ab" if resume else "wb") as target:
                    for chunk in response.iter_bytes(1024 * 1024):
                        target.write(chunk)
            if expected and digest(partial) != expected:
                raise ValueError(f"Checksum mismatch: {destination.name}")
            partial.replace(destination)
            print(f"downloaded: {destination.name} ({destination.stat().st_size // 1048576} MB)", flush=True)
            return
        except (httpx.HTTPError, ValueError) as error:
            print(f"retry {attempt + 1}: {destination.name}: {type(error).__name__}", flush=True)
            time.sleep(2)
    raise RuntimeError(f"Download did not finish: {destination.name}; run again to resume")


def download_large(url, destination, expected):
    if destination.exists() and digest(destination) == expected:
        print(f"ready: {destination.name}", flush=True)
        return
    head = httpx.head(url, follow_redirects=True, timeout=60)
    head.raise_for_status()
    size = int(head.headers["content-length"])
    chunks = destination.parent / (destination.name + ".chunks")
    chunks.mkdir(exist_ok=True)
    block = 8 * 1024 * 1024

    def fetch(index):
        start, end = index * block, min(size, (index + 1) * block) - 1
        path = chunks / str(index)
        if path.exists() and path.stat().st_size == end - start + 1:
            return
        for attempt in range(15):
            try:
                response = httpx.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=90, follow_redirects=True)
                response.raise_for_status()
                if response.status_code != 206 or response.headers.get("content-range") != f"bytes {start}-{end}/{size}":
                    raise ValueError("Unexpected download range")
                if len(response.content) != end - start + 1:
                    raise ValueError("Incomplete download range")
                path.write_bytes(response.content)
                if index % 10 == 0:
                    print(f"{destination.name}: chunk {index + 1}/{(size + block - 1) // block}", flush=True)
                return
            except (httpx.HTTPError, ValueError):
                time.sleep(1 + attempt)
        raise RuntimeError(f"Could not download {destination.name} chunk {index}")

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fetch, i) for i in range((size + block - 1) // block)]
        for future in futures:
            future.result()
    partial = destination.with_suffix(destination.suffix + ".partial")
    with partial.open("wb") as output:
        for i in range((size + block - 1) // block):
            with (chunks / str(i)).open("rb") as part:
                while data := part.read(1024 * 1024):
                    output.write(data)
    if digest(partial) != expected:
        raise RuntimeError(f"Checkpoint checksum mismatch: {destination.name}")
    partial.replace(destination)
    for part in chunks.iterdir():
        part.unlink()
    chunks.rmdir()
    print(f"verified: {destination.name}", flush=True)


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    source = ROOT / "third_party" / "shap-e-main" / "shap_e" / "models" / "download.py"
    constants = {}
    for node in ast.parse(source.read_text("utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("MODEL_PATHS", "CONFIG_PATHS", "URL_HASHES"):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    names = ("text300M", "decoder") if "--text-only" in sys.argv else ("text300M", "decoder", "image300M")
    urls = [constants["MODEL_PATHS"][name] for name in names]
    urls += [constants["CONFIG_PATHS"][name] for name in ("text300M", "decoder", "diffusion", "image300M")]
    clip_source = ROOT / "third_party" / "CLIP-main" / "clip" / "clip.py"
    for node in ast.parse(clip_source.read_text("utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "_MODELS":
            clip_models = ast.literal_eval(node.value)
    clip_url = clip_models["ViT-L/14"]
    jobs = [(url, CACHE / url.rsplit("/", 1)[1], constants["URL_HASHES"][url]) for url in urls]
    jobs.append((clip_url, CACHE / "ViT-L-14.pt", clip_url.split("/")[-2]))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(download_large if job[1].suffix == ".pt" else download, *job) for job in jobs]
        for future in futures:
            future.result()
    (CACHE / "manifest.json").write_text(json.dumps({path.name: checksum for _, path, checksum in jobs}, indent=2), "utf-8")
    print("All Shap-E checkpoints verified.", flush=True)


if __name__ == "__main__":
    main()
