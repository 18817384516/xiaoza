"""Install the official portable Blender build inside this project."""
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_generator import download_large

ROOT = Path(__file__).resolve().parent.parent
VERSION = "4.5.16"
NAME = f"blender-{VERSION}-windows-x64"
SHA256 = "e258e90a1ebc14798ad65b3426bc5f11f5e0e013541c61cc7c3ee9bbf4ca0ce6"


def main():
    destination = ROOT / "third_party" / NAME
    if (destination / "blender.exe").exists():
        print(f"Blender is ready: {destination / 'blender.exe'}", flush=True)
        return
    cache = ROOT / ".runtime" / "install"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / (NAME + ".zip")
    download_large(f"https://download.blender.org/release/Blender4.5/{NAME}.zip", archive, SHA256)
    print("Extracting the verified Blender archive...", flush=True)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            target = (ROOT / "third_party" / item.filename).resolve()
            if not target.is_relative_to((ROOT / "third_party").resolve()):
                raise ValueError("Unexpected archive path")
        source.extractall(ROOT / "third_party")
    print(f"Blender is ready: {destination / 'blender.exe'}", flush=True)


if __name__ == "__main__":
    main()
