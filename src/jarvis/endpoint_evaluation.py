"""Replay consented WAVs through the capture normalizer, VAD and endpoint.

No microphone, transcription, player or tool execution. Continuity of VAD
activity is a technical check, not proof that a human intention is complete.
"""
import argparse
import json
import math
import os
from pathlib import Path
import tempfile
from time import monotonic
import wave

from .audio_endpoint import AudioEndpoint, TurnLimitError
from .stt_corpus import load_corpus, describe, fingerprint, outside_git


def _replay(sample, *, silence_ms, max_seconds, threshold, tail_silence_ms, activity_factory):
    import numpy as np
    from .audio_activity import PCMNormalizer, SileroActivity
    from .voice import WakeWordConversation

    activity = activity_factory() if activity_factory else SileroActivity(threshold=threshold)
    normalizer = PCMNormalizer(sample['rate'], 16000)
    retained = 0
    def store(pcm):
        nonlocal retained
        retained += len(pcm)
    endpoint = AudioEndpoint(16000, silence_seconds=silence_ms / 1000,
                             max_seconds=max_seconds, chunk_sink=store)
    processed = 0
    decision_at = None
    first_active = last_active = None
    late_blocks = 0
    limit_reached = False
    started_at = monotonic()

    def feed(pcm, *, source):
        nonlocal processed, decision_at, first_active, last_active, late_blocks, limit_reached
        if not len(pcm):
            return
        active = activity.active(pcm)
        processed += len(pcm)
        if active and source:
            if first_active is None:
                first_active = processed - len(pcm)
            last_active = processed
            if decision_at is not None:
                late_blocks += 1
        if decision_at is None and not limit_reached:
            try:
                if endpoint.feed(pcm, active):
                    decision_at = processed
            except TurnLimitError:
                limit_reached = True

    with wave.open(str(sample['path'])) as audio:
        blocksize = round(WakeWordConversation.FRAME_SAMPLES * sample['rate'] / 16000)
        while data := audio.readframes(blocksize):
            pcm = np.frombuffer(data, dtype='<i2').astype(np.int16).reshape(-1, sample['channels'])
            feed(normalizer.feed(pcm), source=True)
        feed(normalizer.flush(), source=True)
    source_samples = processed
    remaining = round(tail_silence_ms * 16)
    while remaining:
        size = min(remaining, WakeWordConversation.FRAME_SAMPLES)
        feed(np.zeros(size, dtype=np.int16), source=False)
        remaining -= size

    reason = ('segment_limit' if limit_reached else 'no_activity' if first_active is None
              else 'activity_after_endpoint' if late_blocks else 'endpoint_not_reached' if decision_at is None else '')
    return {'state': 'failed' if reason else 'passed', 'reason': reason,
            'source_normalized_samples': source_samples,
            'retained_samples': retained, 'retained_is_executable': False,
            'first_source_activity_s': first_active / 16000 if first_active is not None else None,
            'last_source_activity_s': last_active / 16000 if last_active is not None else None,
            'endpoint_audio_s': decision_at / 16000 if decision_at is not None else None,
            'endpoint_in_padding': decision_at > source_samples if decision_at is not None else False,
            'source_activity_blocks_after_endpoint': late_blocks,
            'segment_pending': limit_reached, 'wall_s': monotonic() - started_at}


def evaluate(manifest, *, silence_ms=1000, max_seconds=120, threshold=.5,
             tail_silence_ms=0, activity_factory=None):
    if (type(silence_ms) is not int or not 600 <= silence_ms <= 1800
            or type(max_seconds) not in (int, float) or not math.isfinite(max_seconds)
            or not silence_ms / 1000 < max_seconds <= 120
            or type(threshold) not in (int, float) or not 0 < threshold <= 1
            or type(tail_silence_ms) is not int or not 0 <= tail_silence_ms <= 5000):
        raise ValueError('Parâmetros de replay inválidos')
    manifest = outside_git(manifest)
    if manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Manifesto excede 4 MiB')
    sha = fingerprint(manifest)
    samples = load_corpus(manifest)  # Validate all references/consent before loading VAD.
    if fingerprint(manifest) != sha:
        raise ValueError('Manifesto mudou durante a validação')
    rows = []
    for index, sample in enumerate(samples):
        if fingerprint(sample['path']) != sample['sha256']:
            raise ValueError('Áudio mudou antes do replay')
        row = _replay(sample, silence_ms=silence_ms, max_seconds=max_seconds, threshold=threshold,
                      tail_silence_ms=tail_silence_ms, activity_factory=activity_factory)
        if fingerprint(sample['path']) != sample['sha256']:
            raise ValueError('Áudio mudou durante o replay')
        rows.append({'sample_index': index, **row})
    if fingerprint(manifest) != sha:
        raise ValueError('Manifesto mudou durante o replay')
    return {'kind': 'consented_endpoint_replay', 'schema_version': 1,
            'state': 'passed' if all(row['state'] == 'passed' for row in rows) else 'failed',
            'corpus_sha256': sha, **describe(samples), 'measurements': rows,
            'settings': {'silence_ms': silence_ms, 'max_seconds': max_seconds,
                         'vad_threshold': threshold, 'tail_silence_ms': tail_silence_ms,
                         'frame_ms': 80, 'normalized_rate': 16000},
            'activity_detector': 'injected' if activity_factory else 'silero',
            'audio_or_transcriptions_saved': False, 'defaults_changed': False,
            'physical_bluetooth': 'Não testado', 'stt_accuracy': 'Não testado',
            'wake_word': 'Não testado', 'tool_execution': 'Não testado',
            'limits': 'Replay sem relógio de captura: tempo de áudio difere de tempo de processamento. '
                      'Atividade VAD após o endpoint sinaliza possível corte, não prova fala/intenção. '
                      'Ausência de atividade tardia não comprova completude. EOF não finaliza um turno. '
                      'Padding de silêncio, quando solicitado, é sintético. '
                      'Não exercita dispositivo, filas, overflow, ativação ou retomada de segmentos. '
                      'Último bloco/flush do arquivo pode diferir do stream contínuo.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--silence-ms', type=int, default=1000)
    parser.add_argument('--max-seconds', type=float, default=120)
    parser.add_argument('--vad-threshold', type=float, default=.5)
    parser.add_argument('--tail-silence-ms', type=int, default=0,
                        help='Acrescenta silêncio sintético explicitamente (0–5000 ms); padrão: nenhum')
    parser.add_argument('--output', type=Path, help='Relatório novo, sem substituir arquivo existente')
    args = parser.parse_args(argv)
    try:
        if args.output and os.path.lexists(args.output):
            raise ValueError('Relatório exige arquivo novo')
        result = evaluate(args.corpus, silence_ms=args.silence_ms, max_seconds=args.max_seconds,
                          threshold=args.vad_threshold, tail_silence_ms=args.tail_silence_ms)
        output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix='.endpoint-evaluation-', dir=args.output.parent)
            try:
                with os.fdopen(descriptor, 'w') as stream:
                    stream.write(output)
                os.link(name, args.output)  # Complete report, exclusive destination.
            finally:
                Path(name).unlink(missing_ok=True)
        print(output)
    except KeyboardInterrupt:
        parser.exit(130, 'Replay interrompido; nenhum comando foi executado.\n')
    except Exception as exc:
        parser.exit(1, 'Replay não concluído (' + type(exc).__name__ +
                    '). Confira consentimento, WAV, parâmetros e runtime VAD local.\n')
    if result['state'] != 'passed':
        parser.exit(1)


if __name__ == '__main__':
    main()
