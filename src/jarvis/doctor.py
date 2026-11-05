"""Read-only diagnostics and explicitly scoped, time-bounded active probes."""
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
import wave

KINDS = ('inference', 'stt', 'tts', 'microphone', 'playback')


def safe_url(value):
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ''
        host = '[' + host + ']' if ':' in host else host
        return f'{parsed.scheme}://{host}' + (f':{parsed.port}' if parsed.port else '')
    except ValueError:
        return 'URL inválida'


def collect(config):
    from .preferences import PreferenceStore
    from .kokoro_setup import status as kokoro_status
    from .ollama_setup import binary, root_path
    preferences = PreferenceStore().load().effective()
    checks = []
    def add(name, category, state, action='', required=False):
        checks.append({'id': name, 'category': category, 'state': state,
                       'action': action, 'required': required})
    local = config.profile == 'local'
    add('openjarvis', 'installation', 'OK' if config.openjarvis_python and Path(config.openjarvis_python).is_file() else 'Falta',
        'jarvis-fcc local install-engine', local)
    add('ollama', 'installation', 'OK' if binary() else 'Falta', 'jarvis-fcc local install-ollama', local)
    model_name, _, tag = config.local_model.partition(':')
    weights = root_path() / 'models/manifests/registry.ollama.ai/library' / model_name / (tag or 'latest')
    add('local_weights', 'installation', 'OK' if weights.is_file() else 'Não testado',
        'jarvis-fcc local pull-model ' + config.local_model, local)
    snapshots = Path.home() / '.cache/huggingface/hub' / ('models--Systran--faster-whisper-' + preferences.stt_model) / 'snapshots'
    cached = snapshots.is_dir() and any(path.is_file() for path in snapshots.glob('*/model.bin'))
    add('stt_cache', 'installation', 'OK' if cached else 'Falta', 'jarvis-fcc local install-stt --model ' + preferences.stt_model)
    add('tts', 'configuration', 'OK' if preferences.tts_backend == 'kokoro' and kokoro_status()['assets'] != 'Falta'
        or preferences.tts_backend == 'piper' and bool(preferences.piper_model) and Path(preferences.piper_model).expanduser().is_file()
        else 'Falta', 'Configurações → Voz → Saída')
    add('player', 'installation', 'OK' if shutil.which('paplay' if preferences.output_device else 'aplay') else 'Falta',
        'Instalar/configurar o player da saída selecionada')
    add('routing', 'configuration', 'OK' if local else 'Não testado',
        'Local: sem fallback remoto' if local else 'Verificar o provedor efetivo do FCC', True)
    add('fcc', 'functional', 'Não aplicável' if local else 'Não testado',
        'jarvis-fcc --profile fcc --check-fcc', not local)
    add('inference', 'functional', 'Não testado', 'jarvis-fcc --doctor --active-test inference', True)
    add('microphone', 'physical', 'Não testado', 'Solicitar --active-test microphone')
    add('audible', 'physical', 'Não testado', 'Ouvir a frase no fone e confirmar fisicamente')
    add('wake_word', 'configuration', 'Não testado', 'Avaliar Jarvis isolado; fallback STT identificado')
    add('clap', 'physical', 'Não testado', 'Ensaiar palmas e negativos na sessão preparada')
    add('gnome', 'physical', 'Não testado' if platform.system() == 'Linux' else 'Não aplicável',
        'Verificar portais/permissões GNOME na sessão real')
    present = lambda name: importlib.util.find_spec(name) is not None
    return {'application': 'jarvis-fcc', 'module': str(Path(__file__).with_name('cli.py').resolve()),
        'python': sys.executable, 'workspace': str(config.workspace), 'fcc_url': safe_url(config.url),
        'profile': config.profile, 'local_model': config.local_model, 'ollama_host': safe_url(config.ollama_host),
        'openjarvis_python': config.openjarvis_python or sys.executable,
        'local_inference': 'Não testado (doctor básico não executa inferência)', 'kokoro': kokoro_status(),
        'browser_package_installed': present('playwright'), 'voice_package_installed': present('faster_whisper'),
        'desktop_package_installed': present('dbus_next'), 'platform': platform.system(), 'checks': checks,
        'schema_version': 1}


def human(report):
    labels = {'installation': 'Instalação', 'configuration': 'Configuração',
              'functional': 'Funcional', 'physical': 'Físico'}
    lines = [f"Jarvis Doctor · {report['platform']} · perfil {report['profile']}"]
    for check in report['checks']:
        lines.append(f"{labels[check['category']]} · {check['id']}: {check['state']}" +
                     (' · obrigatório' if check['required'] else '') +
                     (' · ' + check['action'] if check['action'] and check['state'] not in ('OK', 'Não aplicável') else ''))
    for event in report.get('active_tests', []):
        lines.append(f"Teste ativo · {event['id']}: {event['state']}" +
                     (' · ' + event['reason'] if event.get('reason') else ''))
    return '\n'.join(lines)


def active(config, kind, *, sample=None, output=None, timeout=60):
    if kind not in KINDS or not 1 <= timeout <= 300:
        raise ValueError('Teste/prazo Doctor inválido')
    if kind == 'stt' and (sample is None or not Path(sample).is_file()):
        raise ValueError('STT exige --sample com uma amostra consentida existente')
    if output is not None and (kind != 'tts' or Path(output).exists()):
        raise ValueError('--doctor-output exige teste TTS e um arquivo novo')
    payload = {'config': {key: str(value) if isinstance(value, Path) else value for key, value in asdict(config).items()},
               'kind': kind, 'sample': str(sample) if sample else None, 'output': str(output) if output else None}
    process = subprocess.Popen([sys.executable, '-m', 'jarvis.doctor'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        data, _ = process.communicate(json.dumps(payload).encode(), timeout=timeout)
        event = json.loads(data)
        if not isinstance(event, dict) or process.returncode or event.get('state') not in ('OK', 'Falhou'):
            raise ValueError('Protocolo do teste ativo inválido')
        return event
    except subprocess.TimeoutExpired:
        return {'id': kind, 'state': 'Falhou', 'reason': 'timeout', 'audible': 'Não testado'}
    except (ValueError, OSError, TypeError):
        return {'id': kind, 'state': 'Falhou', 'reason': 'probe_failed', 'audible': 'Não testado'}
    finally:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
        process.wait()
        for stream in (process.stdin, process.stdout):
            stream.close()


def _probe(payload):
    from .config import Config
    from threading import Event
    config = payload['config']
    for key in ('workspace', 'db'):
        config[key] = Path(config[key])
    config = Config(**config)
    kind = payload['kind']
    if kind == 'inference':
        from .provider_factory import create_provider
        from .agent import _output_text
        provider = create_provider(config)
        try:
            result = provider.responses({'input': 'Responda apenas: teste concluído.',
                'model': provider.active_model, 'max_output_tokens': 64})
            if not _output_text(result) or any(item.get('type') == 'function_call' for item in result.get('output', [])):
                raise ValueError('Inferência não retornou texto completo')
        finally:
            close = getattr(provider, 'close', None)
            if callable(close): close()
        return {'id': kind, 'state': 'OK', 'network_isolation': 'Não testado'}
    from .voice import VoiceIO
    voice = VoiceIO()
    if kind == 'stt':
        text = voice.transcribe(payload['sample'])
        return {'id': kind, 'state': 'OK' if text.strip() else 'Falhou'}
    if kind == 'microphone':
        path = voice.record(3, allow_silence=True)
        try:
            with wave.open(str(path)) as wav:
                frames = wav.getnframes()
            return {'id': kind, 'state': 'OK' if frames > 0 else 'Falhou', 'speech_understood': 'Não testado'}
        finally:
            path.unlink(missing_ok=True)
    from .tts_engine import synthesize_for
    with tempfile.TemporaryDirectory(prefix='jarvis-doctor-') as directory:
        path = Path(directory) / 'sample.wav'
        synthesize_for(voice, 'Esta é uma amostra de voz em português brasileiro.', path, Event())
        with wave.open(str(path)) as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
        if frames < 1:
            raise ValueError('Síntese vazia')
        if kind == 'playback':
            from .capture import coordinator
            with coordinator.output(Event()):
                voice._run_audio(['paplay', '--device=' + voice.output_device, str(path)] if voice.output_device else ['aplay', '-q', str(path)])
        if payload.get('output'):
            # Exclusive creation also works when /tmp and the target differ in filesystem.
            with open(payload['output'], 'xb') as target, path.open('rb') as source:
                shutil.copyfileobj(source, target)
        return {'id': kind, 'state': 'OK', 'frames': frames, 'rate': rate, 'audible': 'Não testado'}


if __name__ == '__main__':
    import contextlib
    payload = json.loads(sys.stdin.read())
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = _probe(payload)
    except Exception as exc:
        result = {'id': payload.get('kind'), 'state': 'Falhou', 'reason': type(exc).__name__, 'audible': 'Não testado'}
    print(json.dumps(result, ensure_ascii=False))
