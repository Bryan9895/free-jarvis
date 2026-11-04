"""Explicit CPU-runtime/voice setup and WAV test, separate from daily speech."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Event
import uuid
import wave

from .cancellation import CancellationToken, CancelledError
from .kokoro_assets import VERSION, assets_directory, install_assets, verify_assets
from .local_setup import _run, _publish, _installation_lock, _environment

TORCH = '2.8.0+cpu'


def runtime_root():
    return Path(os.getenv('JARVIS_KOKORO_RUNTIME_DIR') or
                '~/.local/share/jarvis-fcc/kokoro-runtime').expanduser().absolute()


def runtime_python(root=None):
    root = Path(root) if root is not None else runtime_root()
    try:
        data = json.loads((root / 'runtime.json').read_text())
        python = Path(data['python'])
        if (data['version'] == 1 and data['kokoro_version'] == VERSION
                and data['torch_version'] == TORCH and python.is_absolute()
                and '..' not in python.parts and python.relative_to(root).parts[0] == 'versions'
                and python.is_file() and os.access(python, os.X_OK)):
            return str(python)
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        pass
    return ''


def inspect_runtime(python, *, token=None):
    env = {**_environment(), 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
           'HF_HUB_DISABLE_TELEMETRY': '1', 'CUDA_VISIBLE_DEVICES': ''}
    result = _run([str(python), '-I', str(Path(__file__).with_name('kokoro_worker.py')), '--inspect'],
                  stage='Verificar runtime Kokoro CPU', token=token or CancellationToken(), timeout=30, env=env)
    try:
        event = json.loads(result)
        info = event['runtime']
        if (not event.get('ok') or info['torch_version'] != TORCH or info['kokoro_version'] != VERSION
                or info['language'] != 'pt-br' or info['espeak'] != 'OK'
                or not (3, 10) <= tuple(info['python_version'][:2]) < (3, 13)):
            raise ValueError('Runtime Kokoro CPU não validado; confira dependências e recursos eSpeak pt-BR')
        return info
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('Runtime Kokoro não validado; instale Kokoro 0.9.4/PyTorch CPU/eSpeak pt-BR') from exc


def install_runtime(*, python='', root=None, offline=False, token=None, progress=print):
    if os.name != 'posix':
        raise RuntimeError('Instalação Kokoro automática ainda aguarda validação Windows')
    token = token or CancellationToken()
    token.check()
    root = Path(root).absolute() if root is not None else runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    with _installation_lock(root, token):
        existing = runtime_python(root)
        if existing:
            try:
                info = inspect_runtime(existing, token=token)
            except (CancelledError, TimeoutError):
                raise
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
                progress('Runtime anterior inválido; preparando substituição sem apagar o anterior.')
            else:
                token.check()
                return {'python': existing, 'reused': True, **info}
        uv = shutil.which('uv')
        if not uv:
            raise RuntimeError('Instale uv antes de provisionar o runtime Kokoro')
        python = python or _run([uv, 'python', 'find', '--offline', '3.12'],
            stage='Localizar Python 3.12 para Kokoro', token=token, timeout=10)
        version = _run([str(python), '-I', '-c', 'import sys; print(".".join(map(str,sys.version_info[:2])))'],
            stage='Verificar Python Kokoro', token=token, timeout=10)
        if not (3, 10) <= tuple(map(int, version.split('.'))) < (3, 13):
            raise ValueError('Kokoro 0.9.4 exige Python 3.10–3.12; informe --python CAMINHO')
        destination = root / 'versions' / uuid.uuid4().hex
        try:
            progress('Criando ambiente Kokoro CPU isolado…')
            _run([uv, 'venv', '--offline', '--python', str(python), str(destination)],
                 stage='Criar runtime Kokoro', token=token, timeout=30)
            executable = destination / 'bin/python'
            base = [uv, 'pip', 'install', '--no-config', '--python', str(executable)]
            if offline:
                base.append('--offline')
            progress('Instalando PyTorch CPU fixado…')
            _run([*base, '--index-url', 'https://download.pytorch.org/whl/cpu', f'torch=={TORCH}'],
                 stage='Instalar PyTorch CPU', token=token)
            progress('Instalando Kokoro, Misaki e recursos de fonemização…')
            _run([*base, f'kokoro=={VERSION}', 'misaki[en]==0.9.4', 'transformers==4.51.3'],
                 stage='Instalar Kokoro', token=token)
            info = inspect_runtime(executable, token=token)
            token.check()
            _publish(root, {'version': 1, 'python': str(executable), **info})
            return {'python': str(executable), 'reused': False, **info}
        finally:
            if destination.exists() and runtime_python(root) != str(destination / 'bin/python'):
                shutil.rmtree(destination)


def status():
    from .preferences import PreferenceStore
    preferences = PreferenceStore().load().effective()
    python = preferences.kokoro_python or runtime_python()
    directory = assets_directory(preferences.kokoro_directory or None)
    return {'selected_backend': preferences.tts_backend,
            'runtime': 'Configurado; teste pendente' if python and Path(python).is_file() else 'Falta',
            'assets': 'Presentes; integridade funcional pendente' if (directory / 'SOURCE.json').is_file() else 'Falta',
            'voice': 'pf_dora', 'synthesis': 'Não testado', 'audible': 'Não testado'}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='jarvis-fcc kokoro')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status', help='Diagnóstico básico, sem carregar modelo ou tocar áudio')
    install = sub.add_parser('install-runtime', help='Instala dependências CPU em ambiente isolado')
    install.add_argument('--python', default='')
    install.add_argument('--offline', action='store_true')
    voice = sub.add_parser('install-voice', help='Baixa explicitamente pesos e pf_dora fixados')
    voice.add_argument('--directory')
    use = sub.add_parser('select', help='Salvar Kokoro verificado como voz; não reproduz áudio')
    use.add_argument('--directory')
    use.add_argument('--python', default='')
    test = sub.add_parser('test', help='Síntese explícita de frase controlada para WAV, sem reprodução')
    test.add_argument('--output', type=Path, required=True)
    test.add_argument('--directory')
    args = parser.parse_args(argv)
    cancel = Event()
    token = CancellationToken(event=cancel)
    progress = lambda text: print(text, file=sys.stderr, flush=True)
    try:
        if args.command == 'status':
            result = status()
        elif args.command == 'install-runtime':
            result = install_runtime(python=args.python, offline=args.offline, token=token, progress=progress)
        elif args.command == 'install-voice':
            directory = install_assets(root=args.directory, cancel=cancel, progress=progress)
            result = {'directory': str(directory), 'voice': 'pf_dora', 'synthesis': 'Não testado'}
        elif args.command == 'select':
            from dataclasses import replace
            from .preferences import PreferenceStore
            directory = assets_directory(args.directory)
            verify_assets(directory)
            python = args.python or os.getenv('JARVIS_KOKORO_PYTHON') or runtime_python()
            if not python:
                raise ValueError('Execute kokoro install-runtime antes de selecionar')
            inspect_runtime(python, token=token)
            store = PreferenceStore()
            saved = store.load()
            if store.error:
                raise ValueError('Preferências não carregadas; corrija o arquivo antes de selecionar uma voz')
            store.save(replace(saved, tts_backend='kokoro', kokoro_directory=str(directory), kokoro_python=str(python)))
            result = {'selected': 'kokoro', 'voice': 'pf_dora', 'audible': 'Não testado'}
        else:
            from .kokoro_engine import kokoro_synthesizer
            from .preferences import PreferenceStore
            preferences = PreferenceStore().load().effective()
            target = args.output.expanduser().absolute()
            if target.exists():
                raise ValueError('Escolha um WAV que ainda não exista')
            descriptor, temporary = tempfile.mkstemp(prefix='.kokoro-test-', suffix='.wav', dir=target.parent)
            os.close(descriptor)
            try:
                kokoro_synthesizer.synthesize(assets_directory(args.directory or preferences.kokoro_directory or None),
                    'A voz local está configurada. Esta é uma amostra em português brasileiro.',
                    temporary, cancel, python=preferences.kokoro_python)
                with wave.open(temporary) as wav:
                    if wav.getframerate() != 24000 or wav.getnframes() == 0:
                        raise ValueError('WAV Kokoro inválido')
                    frames = wav.getnframes()
                os.link(temporary, target)  # no-clobber publication
                result = {'output': str(target), 'frames': frames, 'synthesis': 'OK', 'audible': 'Não testado'}
            finally:
                Path(temporary).unlink(missing_ok=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        token.cancel()
        parser.exit(130, 'Kokoro interrompido.\n')
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, str(exc) + '\n')
