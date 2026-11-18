"""Audit the exact files of a public source directory or archive. Stdlib only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

PRIVATE_PARTS = {'data', '.runtime', '.venv', 'node_modules', 'third_party', '__pycache__',
                 '.pytest_cache', 'test-results', 'playwright-report', '.git', 'dist'}
TEXT_SUFFIXES = {'.py', '.ts', '.tsx', '.mjs', '.json', '.md', '.yml', '.yaml', '.toml',
                 '.ps1', '.cmd', '.html', '.css', '.svg', '.txt'}
KEY_PATTERN = re.compile(rb'(?<![A-Za-z0-9])(?:sk-|msy_)[A-Za-z0-9_-]{24,}')
LOCAL_PATH = re.compile(rb'[A-Za-z]:[\\/](?:Users[\\/][^\\/\s]+|td[\\/])', re.I)


def audit(files, configured_secrets=()):
    problems = []
    for name, content in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name:
            problems.append(f'Unsafe path: {name}')
        if any(part.casefold() in PRIVATE_PARTS for part in path.parts):
            problems.append(f'Private or generated directory: {name}')
        if path.name == 'settings.json' or (path.name.startswith('.env') and path.name != '.env.example'):
            problems.append(f'Private configuration: {name}')
        if path.suffix.lower() in {'.pem', '.key', '.log', '.blend', '.pt', '.bin', '.zip', '.pyc'}:
            problems.append(f'Unreviewed private/binary artifact: {name}')
        if len(content) > 20_000_000:
            problems.append(f'File exceeds source repository limit: {name}')
        if any(secret and secret in content for secret in configured_secrets):
            problems.append(f'Configured secret found in {name}')
        if path.suffix.lower() in TEXT_SUFFIXES:
            if KEY_PATTERN.search(content):
                problems.append(f'Credential-like token in {name}')
            if LOCAL_PATH.search(content):
                problems.append(f'Personal absolute path in {name}')
    for name, content in files.items():
        if name == 'PUBLIC_MANIFEST.json':
            try:
                manifest = json.loads(content)
                expected = manifest['sha256']
                actual = {n: hashlib.sha256(c).hexdigest() for n, c in files.items() if n != name}
                if expected != actual:
                    problems.append('Public manifest does not match source files')
            except (ValueError, KeyError, TypeError):
                problems.append('Invalid public manifest')
    return problems


def read_public(path):
    if path.is_dir():
        return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file()}
    with zipfile.ZipFile(path) as archive:
        result = {}
        for item in archive.infolist():
            if item.is_dir():
                continue
            if not item.filename.startswith('xiaozao/'):
                raise ValueError('Unexpected source archive prefix')
            name = item.filename[len('xiaozao/'):]
            if name in result:
                raise ValueError('Duplicate source archive entry')
            result[name] = archive.read(item)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    files = read_public(args.path)
    problems = audit(files)
    if problems:
        raise SystemExit('\n'.join(problems))
    print(f'Public source audit passed: {len(files)} files; no detected private content.')


if __name__ == '__main__':
    main()
