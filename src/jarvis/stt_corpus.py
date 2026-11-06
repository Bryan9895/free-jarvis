"""Consent-bound WAV evaluation. No microphone, player, tools or raw-text logs."""
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from time import monotonic, process_time
import wave

from .latency import summary
from .stt_evaluation import word_errors, critical_values, critical_assessment


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def outside_git(path):
    path = Path(path).resolve()
    for parent in path.parents:
        marker = parent / '.git'
        repository = marker.is_dir() and (marker / 'HEAD').is_file() and (marker / 'objects').is_dir()
        if marker.is_file():
            with marker.open('rb') as stream:
                repository = stream.read(64).startswith(b'gitdir:')
        if repository:
            raise ValueError('Corpus, áudio e transcrições devem ficar fora de repositórios Git')
    return path


def wav_info(path):
    with wave.open(str(path)) as wav:
        channels, width, rate, count = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
        if channels not in (1, 2) or width != 2 or not 8000 <= rate <= 96000 or not 0 < count <= rate * 600:
            raise ValueError('Amostra exige WAV PCM16 mono/estéreo, 8–96 kHz e duração até 10 minutos')
        quiet, prior_signal, quiet_runs, read = 0, False, [], 0
        while data := wav.readframes(max(1, round(rate * .02))):
            values = array('h', data)
            if sys.byteorder != 'little': values.byteswap()
            if len(values) % channels:
                raise ValueError('WAV contém quadro incompleto')
            samples = len(values) // channels
            read += samples
            if channels == 2:
                values = [(values[i] + values[i + 1]) / 2 for i in range(0, len(values), 2)]
            rms = math.sqrt(sum(value * value for value in values) / max(1, len(values)))
            if rms <= 150:
                if prior_signal: quiet += samples
            else:
                if quiet: quiet_runs.append(quiet * 1000 / rate)
                quiet, prior_signal = 0, True
        if read != count:
            raise ValueError('WAV incompleto; nenhuma amostra parcial será avaliada')
    return {'duration_s': count / rate, 'rate': rate, 'channels': channels,
            'internal_quiet_800ms': any(700 <= duration <= 900 for duration in quiet_runs)}


def load_corpus(manifest):
    manifest = outside_git(manifest)
    if manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Manifesto excede 4 MiB')
    rows = json.loads(manifest.read_text())
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError('Corpus exige entre 1 e 200 amostras')
    samples = []
    for index, row in enumerate(rows):
        if (not isinstance(row, dict) or row.keys() - {'audio', 'reference', 'consent', 'source_kind', 'duration_class', 'pause_ms', 'sha256'}
                or row.get('consent') is not True or not isinstance(row.get('audio'), str)
                or not isinstance(row.get('reference'), str) or not row['reference'].strip()
                or len(row['reference']) > 16000 or len(row['reference'].split()) > 2000):
            raise ValueError(f'Amostra {index + 1}: audio, reference não vazia e consent=true são obrigatórios')
        source = row.get('source_kind', 'unspecified')
        if source not in ('human', 'synthetic', 'unspecified'):
            raise ValueError('source_kind deve ser human, synthetic ou unspecified')
        duration = row.get('duration_class')
        if duration is not None and (type(duration) is not int or duration not in (3, 10, 25, 60)):
            raise ValueError('duration_class deve ser 3, 10, 25 ou 60')
        if 'pause_ms' in row and (type(row['pause_ms']) is not int or row['pause_ms'] != 800):
            raise ValueError('A pausa dirigida deve ser pause_ms=800')
        path = outside_git(manifest.parent / row['audio'])
        if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError(f'Amostra {index + 1}: WAV ausente ou maior que 64 MiB')
        sha = fingerprint(path)
        info = wav_info(path)
        if fingerprint(path) != sha:
            raise ValueError('Amostra mudou durante a validação')
        if row.get('sha256', sha) != sha:
            raise ValueError(f'Amostra {index + 1}: SHA256 não confere')
        if duration is not None and abs(info['duration_s'] - duration) > max(.3, duration * .1):
            raise ValueError(f'Amostra {index + 1}: duração não corresponde à classe declarada')
        if row.get('pause_ms') == 800 and not info['internal_quiet_800ms']:
            raise ValueError(f'Amostra {index + 1}: pausa interna de nível baixo entre 700 e 900 ms não observada')
        samples.append({'path': path, 'reference': row['reference'], 'source_kind': source,
                        'duration_class': duration, 'pause_ms': row.get('pause_ms'), 'sha256': sha, **info})
    return samples


def describe(samples):
    human = [sample for sample in samples if sample['source_kind'] == 'human']
    missing = sorted({3, 10, 25, 60} - {sample['duration_class'] for sample in human})
    pause = any(sample['pause_ms'] == 800 and sample['internal_quiet_800ms'] for sample in human)
    numeric = any(critical_values(sample['reference'])['numbers'] for sample in human)
    negative = any(critical_values(sample['reference'])['negations'] for sample in human)
    return {'samples': [
        {key: sample[key] for key in ('sha256', 'source_kind', 'duration_class', 'duration_s', 'rate', 'channels', 'internal_quiet_800ms')}
        for sample in samples], 'human_coverage': {
            'state': 'complete' if not missing and pause and numeric and negative else 'pending',
            'missing_duration_classes': missing, 'pause_800ms': pause, 'numbers': numeric, 'negations': negative}}


def evaluate(manifest, *, model='small', beams=(5,), repetitions=1, vad_filter=True, voice_factory=None):
    if model not in ('tiny', 'base', 'small') or type(repetitions) is not int or not 1 <= repetitions <= 30:
        raise ValueError('Modelo/repetições inválidos')
    beams = list(dict.fromkeys(beams))
    if not beams or any(type(beam) is not int or beam not in (1, 3, 5) for beam in beams):
        raise ValueError('Beams devem ser 1, 3 ou 5')
    if os.getenv('JARVIS_WHISPER_MODEL', model) != model:
        raise ValueError('JARVIS_WHISPER_MODEL conflita com --model; ajuste o ambiente')
    manifest = outside_git(manifest)
    if manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Manifesto excede 4 MiB')
    manifest_sha = fingerprint(manifest)
    samples = load_corpus(manifest)  # Validate the entire set before loading a model.
    if fingerprint(manifest) != manifest_sha:
        raise ValueError('Manifesto mudou durante a validação')
    if voice_factory is None:
        from .voice import VoiceIO
        voice_factory = VoiceIO
    voice = voice_factory(model=model)
    profiles = {beam: [] for beam in beams}
    first_attempt = True
    for repeat in range(repetitions):
        for index, sample in enumerate(samples):
            order = beams if (index + repeat) % 2 else list(reversed(beams))
            for beam in order:
                if fingerprint(sample['path']) != sample['sha256']:
                    raise ValueError('Amostra mudou durante a avaliação; relatório invalidado')
                started, cpu = monotonic(), process_time()
                failed, text = False, ''
                try:
                    text = voice.transcribe(sample['path'], beam_size=beam, vad_filter=vad_filter)
                    if not isinstance(text, str) or len(text) > 32000:
                        raise ValueError('Transcrição excede o limite de avaliação')
                except Exception:
                    failed = True
                    text = ''
                elapsed, cpu_elapsed = monotonic() - started, process_time() - cpu
                if fingerprint(sample['path']) != sample['sha256']:
                    raise ValueError('Amostra mudou durante a transcrição; relatório invalidado')
                errors, words = word_errors(sample['reference'], text)
                critical = critical_values(sample['reference'])
                assessment = {key: matched and not failed for key, matched in
                              critical_assessment(sample['reference'], text).items()}
                profiles[beam].append({'sample_index': index, 'repeat': repeat, 'seconds': elapsed,
                    'cpu_s': cpu_elapsed, 'word_errors': errors, 'reference_words': words,
                    'critical_reference': bool(critical['numbers'] or critical['negations']),
                    'critical_match': not failed and all(assessment.values()), **assessment,
                    'failed': failed, 'includes_cold_load': first_attempt})
                first_attempt = False
    if fingerprint(manifest) != manifest_sha:
        raise ValueError('Manifesto mudou durante a avaliação; relatório invalidado')
    result = {'kind': 'consented_stt_corpus', 'schema_version': 2, 'model': voice.model_name,
        'vad_filter': vad_filter, 'audio_or_transcriptions_saved': False, 'defaults_changed': False,
        'corpus_sha256': manifest_sha, **describe(samples), 'profiles': {},
        'physical_bluetooth': 'Não testado', 'wake_word': 'Não testado',
        'limits': 'Duração é do arquivo, não da fala. Quietude por RMS não comprova fala/VAD. '
                  'Origem humana é declarada no manifesto. Primeira tentativa inclui carga sob demanda em CLI nova; '
                  'cache do SO não é limpo. STT de arquivo não mede endpoint, Bluetooth ou primeiro áudio.'}
    for beam, measurements in profiles.items():
        critical = [row for row in measurements if row['critical_reference']]
        result['profiles'][beam] = {'n': len(measurements),
            'wer': sum(row['word_errors'] for row in measurements) / max(1, sum(row['reference_words'] for row in measurements)),
            'critical_samples': len(critical),
            'critical_match_rate': sum(row['critical_match'] for row in critical) / len(critical) if critical else None,
            'critical_status': ('passed' if all(row['critical_match'] for row in critical) else 'failed') if critical else 'unmeasured',
            'failures': sum(row['failed'] for row in measurements),
            'warm_seconds': summary([row['seconds'] for row in measurements if not row['includes_cold_load']]),
            'measurements': measurements}
    return result
