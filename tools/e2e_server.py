"""Run browser tests against disposable state, never personal settings or jobs."""
from pathlib import Path
import os
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.blender_bridge import find_blender


def main():
    if not (ROOT / 'dist/index.html').is_file():
        raise SystemExit('Run npm run build before browser tests.')
    with tempfile.TemporaryDirectory(prefix='xiaozao-e2e-') as temporary:
        work = Path(temporary)
        shutil.copytree(ROOT / 'server', work / 'server', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(ROOT / 'dist', work / 'dist')
        environment = {key: value for key, value in os.environ.items()
                       if key not in ('OPENAI_API_KEY', 'MESHY_API_KEY')}
        blender = find_blender()
        if blender:
            environment['XIAOZAO_BLENDER_PATH'] = str(blender)
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'server.app:app', '--host',
                                    '127.0.0.1', '--port', '8766'], cwd=work, env=environment)
        def stop(signum, frame):
            raise SystemExit(0)
        for name in (signal.SIGINT, signal.SIGTERM):
            signal.signal(name, stop)
        try:
            raise SystemExit(process.wait())
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)


if __name__ == '__main__':
    main()
