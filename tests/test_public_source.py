"""The public packager must not carry local secrets, paths or project history."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from check_public import audit
from package_open_source import public_example


def test_public_audit_rejects_private_content_without_echoing_secret():
    secret = b'configured-provider-token-value'
    issues = audit({'data/settings.json': b'{}', 'docs/screen.txt': secret}, [secret])
    assert len(issues) >= 2
    assert not any(secret.decode() in issue for issue in issues)
    assert audit({'docs/screen.txt': b'Q:' + b'/Users/' + b'private-user/desktop'})
    assert audit({'../escape.py': b''})


def test_example_publication_drops_user_images_ids_and_edit_history():
    source = {'id': 'private-job', 'created_at': 1, 'thumbnail': True,
              'recipe': {'kind': 'blender', 'name': '演示', 'code': 'def create_model(): return []',
                         'prompt': '公开演示', 'params': {}, 'reference': 'private-image',
                         'edits': ['private-revision'], 'source_job': 'private-job'},
              'stats': {'dimensions': [10, 20, 30], 'warnings': ['private-error'], 'generation_seconds': 30}}
    public = json.loads(public_example(json.dumps(source), 'example'))
    encoded = json.dumps(public)
    assert 'private-' not in encoded
    assert 'thumbnail' not in public
    assert len(public['id']) == 32 and public['recipe']['code'] == source['recipe']['code']


def test_public_manifest_detects_modified_or_injected_file():
    import hashlib
    manifest = json.dumps({'sha256': {'README.md': hashlib.sha256(b'public').hexdigest()}}).encode()
    assert not audit({'README.md': b'public', 'PUBLIC_MANIFEST.json': manifest})
    assert audit({'README.md': b'changed', 'PUBLIC_MANIFEST.json': manifest})
    assert audit({'README.md': b'public', 'injected.txt': b'extra', 'PUBLIC_MANIFEST.json': manifest})
