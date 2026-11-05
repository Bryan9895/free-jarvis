"""Explicit user-local Ollama installation. No system service or startup download."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import tarfile
import tempfile
from urllib.request import urlopen
import uuid
import sys

from .cancellation import CancellationToken
from .local_setup import _installation_lock, _publish, _run

SOURCE = 'https://github.com/ollama/ollama'


def root_path():
    return Path(os.getenv('JARVIS_OLLAMA_DIR') or '~/.local/share/jarvis-fcc/ollama').expanduser().absolute()


def binary():
    root = root_path()
    try:
        data = json.loads((root / 'runtime.json').read_text())
        path = Path(data['executable'])
        if (data['source'] == SOURCE and path.is_absolute() and '..' not in path.parts
                and path.relative_to(root).parts[0] == 'versions' and path.is_file()
                and os.access(path, os.X_OK)):
            return str(path)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        pass
    return shutil.which('ollama') or ''


def _digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def install(*, token=None, progress=print):
    token = token or CancellationToken()
    if platform.system() != 'Linux':
        raise ValueError('Instalação gerenciada Ollama ainda é exclusiva do Linux')
    if sys.version_info < (3, 14):
        raise RuntimeError('Este provisionamento .tar.zst requer Python 3.14+; alternativamente instale Ollama pelo guia oficial')
    arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine())
    if arch is None:
        raise ValueError('Arquitetura Ollama não suportada pelo provisionamento')
    root = root_path()
    root.mkdir(parents=True, exist_ok=True)
    with _installation_lock(root, token):
        try:
            data = json.loads((root / 'runtime.json').read_text())
            executable = binary()
            if data['source'] == SOURCE and executable and _digest(Path(executable)) == data.get('binary_sha256'):
                return {'state': 'OK', 'reused': True, 'version': data['release']}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        token.check()
        progress('Consultando release estável oficial do Ollama…')
        with urlopen('https://api.github.com/repos/ollama/ollama/releases/latest', timeout=15) as response:
            release = json.loads(response.read(4 * 1024 * 1024))
        tag = release['tag_name']
        if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag) or release.get('prerelease') or release.get('draft'):
            raise ValueError('Release Ollama não é estável')
        name = f'ollama-linux-{arch}.tar.zst'
        asset = next((item for item in release['assets'] if item['name'] == name), None)
        if not asset or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or ''):
            raise ValueError('Release sem arquivo/checksum oficial verificável')
        url = asset['browser_download_url']
        if url != f'{SOURCE}/releases/download/{tag}/{name}':
            raise ValueError('Origem inesperada para o binário Ollama')
        destination = root / 'versions' / (tag + '-' + uuid.uuid4().hex[:12])
        destination.mkdir(parents=True)
        try:
            with tempfile.TemporaryDirectory(dir=root, prefix='.download-') as temporary:
                archive = Path(temporary) / name
                progress('Baixando Ollama ' + tag + '…')
                size = 0
                with urlopen(url, timeout=15) as response, archive.open('wb') as output:
                    while True:
                        token.check()
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > 4 * 1024 ** 3:
                            raise ValueError('Arquivo Ollama excede o limite de 4 GiB')
                        output.write(chunk)
                if _digest(archive) != asset['digest'].split(':')[1]:
                    raise ValueError('Checksum do Ollama não confere')
                with tarfile.open(archive) as tar:
                    members = tar.getmembers()
                    if sum(item.size for item in members) > 8 * 1024 ** 3:
                        raise ValueError('Ollama descompactado excede 8 GiB')
                    for member in members:
                        token.check()
                        tar.extract(member, destination, filter='data')
                executable = destination / 'bin/ollama'
                if not executable.is_file() or executable.is_symlink():
                    raise ValueError('Binário Ollama ausente no pacote oficial')
                _run([str(executable), '--help'], stage='Verificar binário Ollama', token=token, timeout=15)
                token.check()
                _publish(root, {'version': 1, 'source': SOURCE, 'release': tag,
                    'archive_sha256': asset['digest'].split(':')[1],
                    'binary_sha256': _digest(executable), 'executable': str(executable)})
                return {'state': 'OK', 'reused': False, 'version': tag}
        finally:
            if binary() != str(destination / 'bin/ollama'):
                shutil.rmtree(destination, ignore_errors=True)


def serve(host, *, token=None):
    from .local_provider import local_host
    from .local_setup import _environment
    executable = binary()
    if not executable:
        raise ValueError('Execute jarvis-fcc local install-ollama primeiro')
    root = root_path()
    home, models = root / 'home', root / 'models'
    home.mkdir(parents=True, exist_ok=True)
    models.mkdir(parents=True, exist_ok=True)
    env = {**_environment(), 'HOME': str(home), 'OLLAMA_HOST': local_host(host),
           'OLLAMA_MODELS': str(models), 'OLLAMA_NO_CLOUD': '1', 'OLLAMA_MAX_LOADED_MODELS': '1',
           'OLLAMA_NUM_PARALLEL': '1', 'CUDA_VISIBLE_DEVICES': '-1'}
    print('Iniciando Ollama em primeiro plano; use Ctrl+C para encerrar.', flush=True)
    _run([executable, 'serve'], stage='Servidor Ollama', token=token or CancellationToken(),
         timeout=86400, env=env)
