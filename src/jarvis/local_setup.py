"""Explicit local-engine provisioning; startup only reads the published pointer.

Environments have immutable paths because moving a venv breaks entry-point
shebangs. Only a verified environment is published, by atomic manifest replace.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Event
from time import monotonic
import uuid

from .cancellation import CancellationToken, CancelledError
from .local_provider import OpenJarvisProvider, OPENJARVIS_REVISION, local_host, local_model

SOURCE = 'https://github.com/open-jarvis/OpenJarvis.git'
REQUIREMENT = f'openjarvis @ git+{SOURCE}@{OPENJARVIS_REVISION}'


def runtime_root(root=None):
    return Path(root or os.getenv('JARVIS_LOCAL_RUNTIME_DIR',
        '~/.local/share/jarvis-fcc/local-runtime')).expanduser().absolute()


def managed_python(root=None):
    """Read-only startup lookup, without subprocesses, sockets or downloads."""
    root = runtime_root(root)
    try:
        manifest = json.loads((root / 'runtime.json').read_text())
        python = Path(manifest['python'])
        if (manifest['version'] != 1 or manifest['revision'] != OPENJARVIS_REVISION
                or manifest['source'] != SOURCE or not python.is_absolute()
                or '..' in python.parts or not python.relative_to(root).parts[0] == 'versions'
                or not python.is_file() or not os.access(python, os.X_OK)):
            return ''
        return str(python)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return ''


def _environment():
    # No API tokens, index overrides, proxy credentials or model routing vars.
    return {key: value for key, value in os.environ.items() if key in
            {'HOME', 'PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT', 'UV_CACHE_DIR'}}


def _run(command, *, stage, token, timeout=900, env=None):
    token.check()
    deadline = min(monotonic() + timeout, token.deadline or float('inf'))
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, env=env or _environment(),
                                       start_new_session=True)
        except OSError as exc:
            raise RuntimeError(f'{stage}: executável indisponível ({type(exc).__name__})') from exc
        try:
            while process.poll() is None:
                token.check()
                if monotonic() >= deadline:
                    raise TimeoutError(f'{stage}: prazo excedido')
                Event().wait(.05)
            token.check()
            if process.returncode:
                # Installer output can contain credential URLs and local paths.
                raise RuntimeError(f'{stage}: falhou (código {process.returncode}); confira rede/cache e dependências')
            output.seek(0)
            return output.read(65536).decode('utf-8', errors='replace').strip()
        finally:
            # Reap git/build subprocesses as well as the installer on Linux.
            if os.name == 'posix':
                import signal
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
            if os.name == 'posix':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def inspect_runtime(python, *, token=None):
    provider = OpenJarvisProvider(python=str(python))
    return provider._exchange({'operation': 'inspect'}, cancel_token=token,
                              deadline=monotonic() + 15)


def _publish(root, data):
    descriptor, name = tempfile.mkstemp(prefix='.runtime-', dir=root)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, root / 'runtime.json')
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def _installation_lock(root, token):
    import fcntl
    with (root / 'install.lock').open('a') as stream:
        deadline = monotonic() + 30
        while True:
            token.check()
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if monotonic() >= deadline:
                    raise TimeoutError('Outra instalação está em andamento; tente novamente após terminar')
                Event().wait(.05)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def install_engine(*, python='', root=None, offline=False, cancel_token=None, progress=print):
    token = cancel_token or CancellationToken()
    token.check()
    root = runtime_root(root)
    if os.name != 'posix':
        raise RuntimeError('Provisionamento automático ainda exige validação nativa no Windows')
    root.mkdir(parents=True, exist_ok=True)
    with _installation_lock(root, token):
        return _install_engine(python=python, root=root, offline=offline, token=token, progress=progress)


def _install_engine(*, python, root, offline, token, progress):
    existing = managed_python(root)
    if existing:
        try:
            info = inspect_runtime(existing, token=token)
        except (CancelledError, TimeoutError):
            raise
        except (RuntimeError, ValueError):
            progress('Ambiente anterior não validado; preparando substituição isolada.')
        else:
            return {'state': 'OK', 'reused': True, 'python': existing, **info}
    uv = shutil.which('uv')
    if not uv:
        raise RuntimeError('Instale uv explicitamente para provisionar o motor isolado')
    if not python:
        python = _run([uv, 'python', 'find', '--offline', '3.13'], stage='Localizar Python 3.13',
                      token=token, timeout=10)
    version = _run([str(python), '-I', '-c', 'import sys; print(".".join(map(str,sys.version_info[:2])))'],
                   stage='Verificar Python', token=token, timeout=10)
    try:
        compatible = (3, 10) <= tuple(map(int, version.split('.'))) < (3, 14)
    except ValueError:
        compatible = False
    if not compatible:
        raise ValueError('O motor fixado exige Python 3.10–3.13; informe --python CAMINHO')
    destination = root / 'versions' / (OPENJARVIS_REVISION[:12] + '-' + uuid.uuid4().hex[:12])
    destination.parent.mkdir(parents=True, exist_ok=True)
    published = False
    try:
        progress('Criando ambiente Python isolado…')
        _run([uv, 'venv', '--offline', '--python', str(python), str(destination)],
             stage='Criar ambiente', token=token, timeout=30)
        executable = destination / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        command = [uv, 'pip', 'install', '--no-config', '--python', str(executable)]
        if offline:
            command.append('--offline')
        command.append(REQUIREMENT)
        progress('Instalando revisão fixada' + (' pelo cache local…' if offline else ' e dependências…'))
        _run(command, stage='Instalar OpenJarvis', token=token)
        progress('Verificando origem, revisão e importação do motor, sem inferência…')
        info = inspect_runtime(executable, token=token)
        if info.get('revision') != OPENJARVIS_REVISION or info.get('engine') != 'ollama':
            raise ValueError('Motor instalado não corresponde à revisão esperada')
        token.check()
        manifest = {'version': 1, 'revision': OPENJARVIS_REVISION, 'source': SOURCE,
                    'python': str(executable), 'package_version': info['package_version']}
        _publish(root, manifest)
        published = True
        return {'state': 'OK', 'reused': False, 'python': str(executable), **info}
    finally:
        if (not published and managed_python(root) != str(destination / 'bin/python')
                and destination.exists()):
            shutil.rmtree(destination)


def status(*, root=None, python=''):
    selected = python or os.getenv('JARVIS_OPENJARVIS_PYTHON') or managed_python(root)
    engine = {'state': 'Falta', 'action': 'jarvis-fcc local install-engine --python CAMINHO'}
    if selected:
        try:
            engine = {'state': 'OK', 'python': selected, **inspect_runtime(selected)}
        except (RuntimeError, ValueError, OSError) as exc:
            engine = {'state': 'Falhou', 'reason': type(exc).__name__,
                      'action': 'Confira a revisão fixada e execute local install-engine'}
    from .ollama_setup import binary
    return {'engine': engine, 'ollama_cli': {'state': 'OK' if binary() else 'Falta'},
            'inference': {'state': 'Não testado', 'action': 'jarvis-fcc local check'},
            'physical_audio': {'state': 'Não testado'}}


def install_stt(model='small', *, token=None, progress=print):
    if model not in ('tiny', 'base', 'small'):
        raise ValueError('Escolha Whisper tiny, base ou small')
    progress('Preparando pesos Whisper ' + model + ' para uso posterior offline…')
    script = 'from faster_whisper.utils import download_model; import sys; download_model(sys.argv[1])'
    _run([sys.executable, '-c', script, model], stage='Preparar Whisper',
         token=token or CancellationToken())
    return {'state': 'OK', 'model': model, 'inference': 'Não testado'}


def pull_model(config, model, *, token=None, progress=print):
    token = token or CancellationToken()
    model, host = local_model(model), local_host(config.ollama_host)
    from .ollama_setup import binary, root_path
    ollama = binary()
    if not ollama:
        raise RuntimeError('Ollama ausente; instale-o antes de baixar pesos')
    progress('Baixando pesos de ' + model + '; aguarde ou use Parar…')
    _run([ollama, 'pull', model], stage='Baixar modelo', token=token, timeout=3600,
         env={**_environment(), 'OLLAMA_HOST': host})
    provider = OpenJarvisProvider(model=model, host=host, python=config.openjarvis_python)
    try:
        identity = provider._exchange({'operation': 'identity', 'model': model}, cancel_token=token)
    finally:
        provider.close()
    root = root_path()
    root.mkdir(parents=True, exist_ok=True)
    with _installation_lock(root, token):
        pointer = root / 'model-pins.json'
        pins = json.loads(pointer.read_text()) if pointer.exists() else {}
        pins[identity['model']] = identity
        fd, name = tempfile.mkstemp(prefix='.model-pins-', dir=root)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(pins, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            token.check()
            os.replace(name, pointer)
        finally:
            Path(name).unlink(missing_ok=True)
    return {'state': 'OK', 'model': model, 'download': 'completed',
            'identity': identity, 'inference': 'Não testado'}


def check(config, *, token=None):
    token = token or CancellationToken()
    provider = OpenJarvisProvider(model=config.local_model, host=local_host(config.ollama_host),
                                 python=config.openjarvis_python)
    try:
        # Select/check through the cancellable exchange rather than initialize(),
        # whose legacy API does not accept a cancellation token.
        models = provider._exchange({'operation': 'models'}, cancel_token=token)
        if config.local_model not in models:
            raise ValueError('Modelo local ausente; baixe os pesos antes de testar')
        provider._exchange({'operation': 'check', 'model': config.local_model}, cancel_token=token)
        response = provider.stream_responses({'input': 'Responda apenas: teste local concluído.',
            'max_output_tokens': 64}, cancel_token=token)
        from .agent import _output_text
        if not _output_text(response) or any(i.get('type') == 'function_call' for i in response.get('output', [])):
            raise ValueError('Teste não retornou uma resposta textual completa')
        token.check()
        return {'state': 'OK', 'model': provider.active_model, 'inference': 'verified',
                'external_network_block': 'Não testado', 'physical_audio': 'Não testado'}
    finally:
        provider.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog='jarvis-fcc local', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    view = commands.add_parser('status', help='Instalação/configuração, sem conectar a Ollama ou capturar áudio')
    view.add_argument('--json', action='store_true')
    install = commands.add_parser('install-engine', help='Provisionar OpenJarvis fixado em venv gerenciada')
    install.add_argument('--python', default='')
    install.add_argument('--offline', action='store_true', help='Somente cache local, sem downloads')
    commands.add_parser('install-ollama', help='Instala release estável com checksum, sem administração')
    stt = commands.add_parser('install-stt', help='Baixa explicitamente Whisper para uso posterior offline')
    stt.add_argument('--model', choices=('tiny', 'base', 'small'), default='small')
    commands.add_parser('serve', help='Inicia Ollama local em primeiro plano; Ctrl+C encerra')
    pull = commands.add_parser('pull-model', help='Baixar explicitamente pesos pelo Ollama instalado')
    pull.add_argument('model')
    commands.add_parser('check', help='Teste ativo: uma inferência textual curta, sem ferramentas ou áudio')
    args = parser.parse_args(argv)
    token = CancellationToken()
    try:
        if args.command == 'status':
            result = status()
            if not args.json:
                for name, entry in result.items():
                    print(f'{name}: {entry["state"]}' + (' · ' + entry['action'] if entry.get('action') else ''))
                return
        elif args.command == 'install-engine':
            result = install_engine(python=args.python, offline=args.offline, cancel_token=token,
                                    progress=lambda text: print(text, file=sys.stderr, flush=True))
        elif args.command == 'install-ollama':
            from .ollama_setup import install as install_ollama
            result = install_ollama(token=token, progress=lambda text: print(text, file=sys.stderr, flush=True))
        elif args.command == 'install-stt':
            result = install_stt(args.model, token=token, progress=lambda text: print(text, file=sys.stderr, flush=True))
        else:
            from .config import Config
            config = Config.from_env()
            host = local_host(config.ollama_host)
            if args.command == 'serve':
                from .ollama_setup import serve
                serve(host, token=token)
                return
            if args.command == 'pull-model':
                result = pull_model(config, args.model, token=token,
                                    progress=lambda text: print(text, file=sys.stderr, flush=True))
            else:
                result = check(config, token=token)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        token.cancel()
        parser.exit(130, 'Preparação interrompida; ambiente anterior preservado.\n')
    except (RuntimeError, ValueError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')
