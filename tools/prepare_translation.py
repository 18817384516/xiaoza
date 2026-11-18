"""Cache the pinned Helsinki-NLP Chinese-to-English translator for offline use."""
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_generator import download

ROOT = Path(__file__).resolve().parent.parent
REVISION = "cf109095479db38d6df799875e34039d4938aaa6"
DEST = ROOT / "data" / "ai_models" / "translation"
DEST.mkdir(parents=True, exist_ok=True)
FILES = ["config.json", "generation_config.json", "pytorch_model.bin", "source.spm", "target.spm", "tokenizer_config.json", "vocab.json"]

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(download, f"https://huggingface.co/Helsinki-NLP/opus-mt-zh-en/resolve/{REVISION}/{name}", DEST / name) for name in FILES]
        for future in futures:
            future.result()
    print("Local Chinese translator ready.", flush=True)
