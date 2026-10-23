"""Instalação explícita de uma voz, sem pacotes do sistema nem startup de rede."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.request import urlopen

from .cancellation import CancelledError

REVISION = '1af0d6b01d3dbe698a426f0c3424650ef77fc131'
BASE_URL = f'https://huggingface.co/rhasspy/piper-voices/resolve/{REVISION}/pt/pt_BR/faber/medium/'
NAME = 'pt_BR-faber-medium'
FILES = {
    NAME + '.onnx': ('858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7', 70_000_000),
    NAME + '.onnx.json': ('7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f', 100_000),
    'MODEL_CARD': (None, 100_000),
}


def _verify(directory):
    for filename, (expected, _limit) in FILES.items():
        path = directory / filename
        if not path.is_file():
            raise ValueError('Arquivo de voz ausente: ' + filename)
        if expected:
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError('Hash inválido: ' + filename)
    config = json.loads((directory / (NAME + '.onnx.json')).read_text())
    if config.get('language', {}).get('code') != 'pt_BR' or config.get('audio', {}).get('sample_rate') != 22050:
        raise ValueError('Configuração incompatível com a voz pt-BR selecionada')
    if 'CC0' not in (directory / 'MODEL_CARD').read_text():
        raise ValueError('Cartão de licença da voz não corresponde ao manifestado')


def install_faber(*, root=None, cancel, progress=lambda _: None):
    root = Path(root or '~/.local/share/jarvis-fcc/voices').expanduser()
    destination = root / NAME
    if cancel.is_set():
        raise CancelledError('Instalação de voz cancelada')
    if destination.exists():
        _verify(destination)
        return destination / (NAME + '.onnx')
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.voice-download-', dir=root))
    try:
        for index, (filename, (_expected, limit)) in enumerate(FILES.items()):
            if cancel.is_set():
                raise CancelledError('Instalação de voz cancelada')
            progress(f'Baixando {filename} ({index + 1}/{len(FILES)})…')
            with urlopen(BASE_URL + filename, timeout=15) as response, (staging / filename).open('wb') as stream:
                total = int(response.headers.get('Content-Length', 0))
                if total > limit:
                    raise ValueError('Arquivo de voz excede o limite esperado')
                received = 0
                while True:
                    if cancel.is_set():
                        raise CancelledError('Instalação de voz cancelada')
                    chunk = response.read(262144)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > limit:
                        raise ValueError('Arquivo de voz excede o limite esperado')
                    stream.write(chunk)
                    progress(f'{filename}: {received // 1024} KiB' + (f' / {total // 1024} KiB' if total else ''))
        _verify(staging)
        (staging / 'SOURCE.json').write_text(json.dumps({'revision': REVISION, 'source': BASE_URL,
            'dataset_license': 'CC0 (MODEL_CARD)', 'repository_license': 'MIT (repository metadata)',
            'sha256': {name: value[0] for name, value in FILES.items() if value[0]}}, indent=2))
        if cancel.is_set():
            raise CancelledError('Instalação de voz cancelada')
        os.replace(staging, destination)
        progress('Voz verificada e instalada. Teste a saída de áudio.')
        return destination / (NAME + '.onnx')
    finally:
        if staging.exists():
            shutil.rmtree(staging)
