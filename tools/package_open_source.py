"""Build a reviewed public source tree without personal data or dependencies."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_public import audit

ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = ['README.md', 'README.en.md', 'LICENSE', 'CONTRIBUTING.md', 'SECURITY.md',
              'CODE_OF_CONDUCT.md', 'CHANGELOG.md', 'THIRD_PARTY_NOTICES.md', '.gitignore',
              '.gitattributes', '.editorconfig', '.prettierrc.json', 'index.html', 'package.json',
              'package-lock.json', 'requirements.txt', 'requirements-ai.txt', 'tsconfig.json',
              'vite.config.ts', 'playwright.config.ts', 'pytest.ini', 'start.ps1', 'stop.ps1',
              'install-blender.ps1', '启动小造.cmd', '停止小造.cmd', '安装Blender建模.cmd']
SOURCE_DIRS = ['src', 'server', 'public', 'tests', 'docs', '.github', 'config']
TOOLS = ['check_public.py', 'package_open_source.py', 'prepare_blender.py', 'prepare_generator.py',
         'prepare_translation.py', 'e2e-server.mjs', 'e2e_server.py', 'capture_public.mjs']
EXAMPLES = ['bunny', 'bracket', 'gear', 'vase', '牛油果椅子', 'U形理线夹-6毫米孔']


def public_example(content, name):
    """Publish only intentional demo fields, not job IDs, references or history."""
    value = json.loads(content)
    recipe_fields = {'kind', 'category', 'name', 'prompt', 'params', 'code', 'summary', 'detail', 'generator'}
    stats_fields = {'dimensions', 'volume_cm3', 'triangles', 'watertight', 'components', 'units'}
    recipe = {key: item for key, item in value['recipe'].items() if key in recipe_fields}
    stats = {key: item for key, item in value['stats'].items() if key in stats_fields}
    stats['warnings'] = ['公开演示示例，尚未进行实物打印、壁厚和承载验证。']
    result = {'id': hashlib.sha256(('public-example:' + name).encode()).hexdigest()[:32],
              'name': recipe['name'], 'created_at': datetime(2026, 11, 19, tzinfo=timezone.utc).timestamp(),
              'recipe': recipe, 'stats': stats}
    return (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()


def collect(root):
    result = {}
    for name in ROOT_FILES:
        result[name] = (root / name).read_bytes()
    for directory in SOURCE_DIRS:
        for path in sorted((root / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                result[path.relative_to(root).as_posix()] = path.read_bytes()
    for name in TOOLS:
        result['tools/' + name] = (root / 'tools' / name).read_bytes()
    result['examples/README.md'] = (root / 'examples/README.md').read_bytes()
    for name in EXAMPLES:
        for suffix in ('.json', '.stl', '.3mf', '.py'):
            path = root / 'examples' / (name + suffix)
            if path.is_file():
                data = path.read_bytes()
                result['examples/' + path.name] = public_example(data, name) if suffix == '.json' else data
        if 'examples/' + name + '.json' not in result or 'examples/' + name + '.stl' not in result:
            raise ValueError(f'Missing public example: {name}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace', action='store_true', help='Replace only the fixed generated public directory')
    args = parser.parse_args()
    version = json.loads((ROOT / 'package.json').read_text('utf-8'))['version']
    files = collect(ROOT)
    secrets = []
    settings = ROOT / 'data/settings.json'
    if settings.is_file():
        config = json.loads(settings.read_text('utf-8'))
        secrets = [str(config[key]).encode() for key in ('api_key', 'meshy_api_key') if config.get(key)]
    problems = audit(files, secrets)
    if problems:
        raise SystemExit('Public packaging stopped:\n' + '\n'.join(problems))
    manifest = {'project': 'xiaozao', 'version': version, 'sha256': {
        name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}}
    files['PUBLIC_MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    target = artifacts / 'xiaozao-open-source'
    if target.is_symlink() or target.resolve() != artifacts.resolve() / 'xiaozao-open-source':
        raise SystemExit('Refusing to replace a redirected output directory.')
    if target.exists():
        if not args.replace:
            raise SystemExit('Public directory already exists. Use --replace to replace this generated output only.')
        marker = target / 'PUBLIC_MANIFEST.json'
        if not marker.is_file() or json.loads(marker.read_text('utf-8')).get('project') != 'xiaozao':
            raise SystemExit('Existing output is not a recognized generated public source tree.')
        # The resolved absolute target above is checked before deleting.
        shutil.rmtree(target)
    target.mkdir()
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    archive_path = artifacts / f'xiaozao-open-source-v{version}.zip'
    with ZipFile(archive_path, 'w', ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr('xiaozao/' + name, content)
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix('.sha256').write_text(f'{checksum}  {archive_path.name}\n', 'utf-8')
    print(f'Public directory: {target}')
    print(f'Public archive: {archive_path} ({archive_path.stat().st_size / 1048576:.2f} MB)')
    print(f'Checked {len(files)} files; configured keys and personal runtime directories excluded.')


if __name__ == '__main__':
    main()
