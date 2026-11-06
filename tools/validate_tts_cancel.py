"""Explicit CPU speech cancellation probe with a WAV sink, never a speaker."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from threading import Timer
from time import monotonic
import wave

from jarvis.cancellation import CancelledError
from jarvis.kokoro_engine import kokoro_synthesizer
from jarvis.project_services import identity
from jarvis.tts_engine import synthesizer
from jarvis.voice import VoiceIO

TEXT = ('Esta é uma resposta longa para verificar a interrupção da síntese e a limpeza da fila. ' * 100)


def probe(voice, engine, *, delay=.15):
    if not math.isfinite(delay) or not .02 <= delay <= 5:
        raise ValueError('Delay deve estar entre 0,02 e 5 segundos')
    observed, late, signal_at, worker = [], [], [], []
    original_player = voice._run_audio
    def sink(command):
        path = Path(command[-1])
        if voice._speech_cancel.is_set(): late.append(True)
        with wave.open(str(path)) as audio:
            if audio.getnframes() < 1: raise ValueError('WAV vazio')
        observed.append(path)
    def stop():
        process = engine._process
        try: pid = process.pid if process else None
        except ValueError: pid = None
        worker.append(identity(pid) if pid and sys.platform == 'linux' else None)
        signal_at.append(monotonic())
        voice.cancel_speech()
    voice._run_audio = sink
    voice.prepare_speech()
    timer = Timer(delay, stop)
    started = monotonic()
    timer.start()
    state = 'completed_before_cancel'
    try:
        try:
            voice.speak(TEXT)
        except CancelledError:
            state = 'cancelled'
        ended = monotonic()
    finally:
        timer.cancel()
        timer.join()
        voice._run_audio = original_player
    before = worker[0] if worker else None
    stopped = identity(before['pid']) != before if before else None
    return {'state': state, 'cancel_delay_s': delay, 'total_s': ended - started,
        'cancel_to_return_s': max(0, ended - signal_at[0]) if signal_at else None,
        'worker_observed': before is not None, 'worker_stopped': stopped,
        'wav_sink_calls': len(observed), 'wav_calls_after_cancel': len(late),
        'observed_wavs_removed': all(not path.exists() for path in observed),
        'physical_playback': 'Não testado',
        'passed': state == 'cancelled' and stopped is True and not late and all(not path.exists() for path in observed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('kokoro', 'piper'), default='kokoro')
    parser.add_argument('--model', type=Path, help='Modelo Piper instalado')
    parser.add_argument('--delay', type=float, default=.15)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'linux': parser.error('Ensaio de identidade de processo exige Linux')
    if args.backend == 'piper' and args.model is None: parser.error('Piper exige --model')
    if not math.isfinite(args.delay) or not .02 <= args.delay <= 5:
        parser.error('--delay deve estar entre 0,02 e 5 segundos')
    voice = VoiceIO(piper_model=str(args.model) if args.model else '')
    voice.tts_backend = args.backend
    from jarvis.kokoro_assets import FILES
    protected = {(voice.kokoro_directory / name).resolve() for name in (*FILES, 'SOURCE.json')}
    if voice.piper_model: protected.add(voice.piper_model.resolve())
    if args.output.resolve() in protected: parser.error('O relatório não pode substituir artefatos de voz')
    engine = kokoro_synthesizer if args.backend == 'kokoro' else synthesizer
    result = {'kind': args.backend + '_wav_sink_cancellation', 'defaults_changed': False,
              'physical_playback': 'Não testado', 'limits': 'Interrupção de síntese/fila sem player físico. '
              'Somente WAVs observados no sink têm limpeza conferida aqui. Não mede Stop na GUI ou Bluetooth.'}
    try:
        if args.backend == 'kokoro':
            from jarvis.kokoro_assets import verify_assets
            result['asset_sha256'] = verify_assets(voice.kokoro_directory)['sha256']
        else:
            digest = hashlib.sha256()
            with voice.piper_model.open('rb') as stream:
                for block in iter(lambda: stream.read(65536), b''): digest.update(block)
            result['asset_sha256'] = {'piper': digest.hexdigest()}
        synthesizer.close()
        kokoro_synthesizer.close()
        result['cold'] = probe(voice, engine, delay=args.delay)
        voice.prepare_speech()
        voice.warmup()  # Recreates a worker after cancellation; no player.
        result['warm'] = probe(voice, engine, delay=args.delay)
        voice.prepare_speech()
        voice.warmup()
        result['recovery_warmup'] = 'passed'
    except (ValueError, RuntimeError, OSError) as exc:
        result.update(error_type=type(exc).__name__, completed=False)
    else:
        result['completed'] = all(result[phase]['passed'] for phase in ('cold', 'warm'))
    finally:
        synthesizer.close()
        kokoro_synthesizer.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.tts-cancel-', dir=args.output.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream: json.dump(result, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, args.output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['completed']: raise SystemExit(1)


if __name__ == '__main__':
    main()
