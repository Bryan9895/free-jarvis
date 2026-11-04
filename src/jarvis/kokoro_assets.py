"""Explicit Kokoro-82M/pf_dora download with pinned upstream files and integrity.

Only stdlib is imported. Reading/validating this module never loads a model.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.request import urlopen

REPOSITORY = 'https://huggingface.co/hexgrad/Kokoro-82M'
MODEL_REVISION = '41e5892b9d8b43e56fc560f892312a328a410973'
VOICE_REVISION = 'a3ebfcc2bb43e3d8df8199d4081f4fc6d310cc6d'
VERSION = '0.9.4'
VOICE = 'pf_dora'
# Hashes published on the official Hugging Face file pages. Small metadata
# files are pinned by immutable revision and hashed on first explicit download.
FILES = {
    'kokoro-v1_0.pth': (MODEL_REVISION, 'kokoro-v1_0.pth',
        '496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4', 340_000_000),
    'pf_dora.pt': (VOICE_REVISION, 'voices/pf_dora.pt',
        '07e4ff987c5d5a8c3995efd15cc4f0db7c4c15e881b198d8ab7f67ecf51f5eb7', 1_000_000),
    'config.json': (MODEL_REVISION, 'config.json', None, 128_000),
    'MODEL_CARD.md': (MODEL_REVISION, 'README.md', None, 100_000),
}


def assets_directory(root=None):
    return Path(root or os.getenv('JARVIS_KOKORO_DIRECTORY') or
        '~/.local/share/jarvis-fcc/voices/kokoro-pf_dora').expanduser().resolve()


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'SOURCE.json').read_text())
    if (manifest.get('version') != 1 or manifest.get('repository') != REPOSITORY
            or manifest.get('model_revision') != MODEL_REVISION
            or manifest.get('voice_revision') != VOICE_REVISION
            or manifest.get('kokoro_version') != VERSION or manifest.get('language') != 'pt-br'
            or manifest.get('voice') != VOICE or manifest.get('license') != 'Apache-2.0'):
        raise ValueError('Manifesto Kokoro não corresponde aos artefatos fixados')
    for name, (_, _, expected, limit) in FILES.items():
        path = directory / name
        if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= limit:
            raise ValueError('Artefato Kokoro ausente/inválido: ' + name)
        recorded = manifest.get('sha256', {}).get(name)
        if (not isinstance(recorded, str) or len(recorded) != 64
                or _hash(path) != (expected or recorded) or expected and recorded != expected):
            raise ValueError('Integridade Kokoro inválida: ' + name)
    config = json.loads((directory / 'config.json').read_text())
    if config.get('n_token') != 178 or config.get('style_dim') != 128:
        raise ValueError('Configuração Kokoro incompatível')
    if 'license: apache-2.0' not in (directory / 'MODEL_CARD.md').read_text().lower():
        raise ValueError('Licença Kokoro não confirmada pelo model card fixado')
    return manifest


def install_assets(*, root=None, cancel, progress=lambda _: None):
    from .cancellation import CancelledError
    directory = assets_directory(root)
    def check():
        if cancel.is_set():
            raise CancelledError('Instalação Kokoro cancelada')
    check()
    if directory.exists():
        verify_assets(directory)
        return directory
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.kokoro-download-', dir=directory.parent))
    try:
        hashes = {}
        for name, (revision, remote, expected, limit) in FILES.items():
            check()
            progress('Baixando Kokoro: ' + name)
            with urlopen(f'{REPOSITORY}/resolve/{revision}/{remote}', timeout=15) as response, \
                    (staging / name).open('wb') as output:
                total = int(response.headers.get('Content-Length', 0))
                if total > limit:
                    raise ValueError('Artefato Kokoro excede o limite: ' + name)
                received = 0
                while True:
                    check()
                    chunk = response.read(262144)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > limit:
                        raise ValueError('Artefato Kokoro excede o limite: ' + name)
                    output.write(chunk)
                    progress(f'{name}: {received // 1024} KiB')
            hashes[name] = _hash(staging / name)
            if expected and hashes[name] != expected:
                raise ValueError('Hash Kokoro inválido: ' + name)
        (staging / 'SOURCE.json').write_text(json.dumps({'version': 1, 'repository': REPOSITORY,
            'model_revision': MODEL_REVISION, 'voice_revision': VOICE_REVISION,
            'kokoro_version': VERSION, 'voice': VOICE, 'language': 'pt-br',
            'license': 'Apache-2.0', 'sha256': hashes}, ensure_ascii=False, indent=2))
        verify_assets(staging)
        check()
        os.rename(staging, directory)
        progress('Kokoro e pf_dora instalados e verificados. Síntese e áudio ainda precisam de teste.')
        return directory
    finally:
        if staging.exists():
            shutil.rmtree(staging)
