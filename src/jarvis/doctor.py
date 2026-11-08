"""Read-only diagnostics and explicitly scoped, time-bounded active probes."""
from dataclasses import asdict
from contextlib import ExitStack
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
from time import monotonic
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
    kokoro = kokoro_status()
    from .elevenlabs_tts import configured as elevenlabs_configured
    tts_ready = (preferences.tts_backend == 'elevenlabs' and elevenlabs_configured()
        or preferences.tts_backend == 'kokoro' and kokoro['assets'] != 'Falta' and kokoro['runtime'] != 'Falta'
        or preferences.tts_backend == 'piper' and bool(preferences.piper_model) and Path(preferences.piper_model).expanduser().is_file())
    add('tts', 'configuration', 'OK' if tts_ready else 'Falta',
        'Defina ELEVENLABS_API_KEY no ambiente (sem persistir a chave)')
    add('player', 'installation', 'OK' if shutil.which('paplay' if preferences.output_device else 'paplay') or
        (not preferences.output_device and shutil.which('aplay')) else 'Falta',
        'Instalar/configurar o player da saída selecionada')
    add('routing', 'configuration', 'OK' if local else 'Não testado',
        'Local: sem fallback remoto' if local else 'Verificar o provedor efetivo do FCC', True)
    add('fcc', 'functional', 'Não aplicável' if local else 'Não testado',
        'jarvis-fcc --profile fcc --check-fcc', not local)
    add('inference', 'functional', 'Não testado', 'jarvis-fcc --doctor --active-test inference', True)
    add('stt', 'functional', 'Não testado', 'jarvis-fcc --doctor --active-test stt --doctor-corpus CORPUS_EXTERNO.json')
    add('tts_synthesis', 'functional', 'Não testado', 'jarvis-fcc --doctor --active-test tts')
    add('playback', 'functional', 'Não testado', 'jarvis-fcc --doctor --active-test playback')
    add('microphone', 'physical', 'Não testado', 'Solicitar --active-test microphone')
    add('audible', 'physical', 'Não testado', 'Ouvir a frase no fone e confirmar fisicamente')
    add('wake_word', 'configuration', 'Não testado', 'Treinar/validar detector acústico de Adam; fallback por STT em uso')
    add('clap', 'physical', 'Não testado', 'Ensaiar palmas e negativos na sessão preparada')
    add('gnome', 'physical', 'Não testado' if platform.system() == 'Linux' else 'Não aplicável',
        'Verificar portais/permissões GNOME na sessão real')
    present = lambda name: importlib.util.find_spec(name) is not None
    return {'application': 'jarvis-fcc', 'module': str(Path(__file__).with_name('cli.py').resolve()),
        'python': sys.executable, 'workspace': str(config.workspace), 'fcc_url': safe_url(config.url),
        'profile': config.profile, 'local_model': config.local_model, 'ollama_host': safe_url(config.ollama_host),
        'stt_model': preferences.stt_model, 'tts_backend': preferences.tts_backend,
        'openjarvis_python': config.openjarvis_python or sys.executable,
        'local_inference': 'Não testado (doctor básico não executa inferência)', 'kokoro': kokoro,
        'browser_package_installed': present('playwright'), 'voice_package_installed': present('faster_whisper'),
        'desktop_package_installed': present('dbus_next'), 'platform': platform.system(), 'checks': checks,
        'schema_version': 1}


def human(report):
    labels = {'installation': 'Instalação', 'configuration': 'Configuração',
              'functional': 'Funcional', 'physical': 'Físico'}
    lines = [f"ADAM Doctor · {report['platform']} · perfil {report['profile']}"]
    lines.append(f"Reconhecimento: {report.get('stt_model', 'Não testado')} · Voz: {report.get('tts_backend', 'Não testado')}")
    for check in report['checks']:
        lines.append(f"{labels[check['category']]} · {check['id']}: {check['state']}" +
                     (' · obrigatório' if check['required'] else '') +
                     (' · ' + check['action'] if check['action'] and check['state'] not in ('OK', 'Não aplicável') else ''))
    for event in report.get('active_tests', []):
        lines.append(f"Teste ativo · {event['id']}: {event['state']}" +
                     (' · ' + event['reason'] if event.get('reason') else '') +
                     (' · ' + event['verification_scope'] if event.get('verification_scope') else ''))
    return '\n'.join(lines)


def merge_active(report, event):
    report.setdefault('active_tests', []).append(event)
    target = 'tts_synthesis' if event['id'] == 'tts' else event['id']
    for check in report['checks']:
        if check['id'] == target and check['category'] in ('functional', 'physical'):
            check['state'] = event['state']


def active(config, kind, *, sample=None, corpus=None, output=None, timeout=60):
    started = monotonic()
    if kind not in KINDS or not 1 <= timeout <= 300:
        raise ValueError('Teste/prazo Doctor inválido')
    if corpus is not None and (kind != 'stt' or sample is not None):
        raise ValueError('--doctor-corpus exige teste STT sem --sample')
    corpus_sha = None
    if corpus is not None:
        from .stt_corpus import outside_git, fingerprint
        corpus = outside_git(corpus)
        if not corpus.is_file() or corpus.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('Corpus externo ausente ou maior que 4 MiB')
        corpus_sha = fingerprint(corpus)
    if kind == 'stt' and corpus is None and (sample is None or not Path(sample).is_file()):
        raise ValueError('STT exige --sample com uma amostra consentida existente')
    if output is not None and (kind != 'tts' or Path(output).exists()):
        raise ValueError('--doctor-output exige teste TTS e um arquivo novo')
    payload = {'config': {key: str(value) if isinstance(value, Path) else value for key, value in asdict(config).items()},
               'kind': kind, 'sample': str(sample) if sample else None, 'corpus': str(corpus) if corpus else None,
               'corpus_sha256': corpus_sha, 'output': str(output) if output else None}
    with ExitStack() as resources:
        payload['temporary_directory'] = resources.enter_context(tempfile.TemporaryDirectory(prefix='jarvis-doctor-probe-'))
        stage = None
        if output is not None:
            descriptor, name = tempfile.mkstemp(prefix='.jarvis-doctor-', suffix='.wav', dir=Path(output).absolute().parent)
            os.close(descriptor)
            stage = Path(name)
            resources.callback(stage.unlink, missing_ok=True)
            payload['output_stage'] = str(stage)
        remaining = timeout - (monotonic() - started)
        if remaining <= 0:
            return {'id': kind, 'state': 'Falhou', 'reason': 'timeout', 'audible': 'Não testado'}
        try:
            process = subprocess.Popen([sys.executable, '-m', 'jarvis.doctor'], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            return {'id': kind, 'state': 'Falhou', 'reason': 'worker_unavailable', 'audible': 'Não testado'}
        try:
            data, _ = process.communicate(json.dumps(payload).encode(), timeout=remaining)
            event = json.loads(data)
            if not isinstance(event, dict) or process.returncode or event.get('id') != kind or event.get('state') not in ('OK', 'Falhou'):
                raise ValueError('Protocolo do teste ativo inválido')
            if stage is not None and event['state'] == 'OK':
                event.update(_wav_facts(stage))
            if monotonic() - started >= timeout:
                raise subprocess.TimeoutExpired('doctor', timeout)
            if stage is not None and event['state'] == 'OK':
                os.link(stage, output)  # Atomic, same filesystem, no replacement of another writer.
            return event
        except subprocess.TimeoutExpired:
            return {'id': kind, 'state': 'Falhou', 'reason': 'timeout', 'audible': 'Não testado'}
        except (ValueError, OSError, TypeError, EOFError, wave.Error):
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


def _wav_facts(path):
    if Path(path).is_symlink() or not Path(path).is_file():
        raise ValueError('WAV precisa ser um arquivo regular')
    if Path(path).stat().st_size > 64 * 1024 * 1024:
        raise ValueError('WAV do diagnóstico excede o limite')
    with wave.open(str(path)) as audio:
        frames, rate, channels = audio.getnframes(), audio.getframerate(), audio.getnchannels()
        if audio.getsampwidth() != 2 or channels not in (1, 2) or not 8000 <= rate <= 96000 or not 0 < frames <= rate * 120:
            raise ValueError('WAV PCM16 inválido no diagnóstico')
        read = sum(len(block) for block in iter(lambda: audio.readframes(65536), b''))
        if read != frames * channels * 2:
            raise ValueError('WAV truncado no diagnóstico')
    return {'frames': frames, 'rate': rate, 'channels': channels}


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
    if kind == 'stt' and payload.get('corpus'):
        from .stt_corpus import evaluate, fingerprint
        from .preferences import PreferenceStore
        if fingerprint(payload['corpus']) != payload.get('corpus_sha256'):
            raise ValueError('Corpus mudou após a solicitação')
        result = evaluate(payload['corpus'], model=PreferenceStore().load().effective().stt_model)
        if result['corpus_sha256'] != payload.get('corpus_sha256'):
            raise ValueError('Corpus mudou após a solicitação')
        profile = result['profiles'][5]
        passed = not profile['failures'] and profile['wer'] == 0 and profile['critical_status'] != 'failed'
        return {'id': 'stt', 'state': 'OK' if passed else 'Falhou',
            'reason': '' if passed else 'transcription_failed' if profile['failures'] else 'reference_mismatch',
            'verification_scope': 'Referência literal e elementos críticos; não comprova entendimento ou Bluetooth',
            'corpus_sha256': result['corpus_sha256'], 'samples': len(result['samples']),
            'model': result['model'],
            'wer': profile['wer'], 'critical_status': profile['critical_status'],
            'critical_match_rate': profile['critical_match_rate'], 'failures': profile['failures'],
            'human_coverage': result['human_coverage']['state'], 'physical_audio': 'Não testado'}
    from .voice import VoiceIO
    voice = VoiceIO()
    if kind == 'stt':
        text = voice.transcribe(payload['sample'])
        return {'id': kind, 'state': 'OK' if text.strip() else 'Falhou',
            'verification_scope': 'Apenas produção de texto; acurácia não testada',
            'reference_check': 'Não testado', 'physical_audio': 'Não testado'}
    if kind == 'microphone':
        path = voice.record(3, allow_silence=True)
        try:
            return {'id': kind, 'state': 'OK', **_wav_facts(path), 'speech_understood': 'Não testado'}
        finally:
            path.unlink(missing_ok=True)
    from .tts_engine import synthesize_for
    with tempfile.TemporaryDirectory(prefix='jarvis-doctor-') as directory:
        path = Path(directory) / 'sample.wav'
        synthesize_for(voice, 'Esta é uma amostra de voz em português brasileiro.', path, Event())
        facts = _wav_facts(path)
        if kind == 'playback':
            from .capture import coordinator
            with coordinator.output(Event()):
                voice._run_audio(['paplay', '--device=' + voice.output_device, str(path)] if voice.output_device else ['aplay', '-q', str(path)])
        if payload.get('output_stage'):
            with open(payload['output_stage'], 'wb') as target, path.open('rb') as source:
                shutil.copyfileobj(source, target)
        return {'id': kind, 'state': 'OK', **facts, 'backend': voice.tts_backend, 'audible': 'Não testado'}


if __name__ == '__main__':
    import contextlib
    payload = json.loads(sys.stdin.read())
    if payload.get('temporary_directory'):
        tempfile.tempdir = payload['temporary_directory']
        # Keep synthesis descendants inside the probe group owned by active().
        # Daily GUI/CLI workers retain their default independent session.
        from .kokoro_engine import kokoro_synthesizer
        kokoro_synthesizer.own_session = False
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = _probe(payload)
    except Exception as exc:
        result = {'id': payload.get('kind'), 'state': 'Falhou', 'reason': type(exc).__name__, 'audible': 'Não testado'}
    print(json.dumps(result, ensure_ascii=False))
