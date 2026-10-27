"""Síntese Piper real e pipeline; sink WAV sem reprodução física."""
import argparse
import hashlib
import json
from pathlib import Path
from time import monotonic
import wave

from jarvis.benchmark import rss_kib
from jarvis.latency import summary
from jarvis.voice import VoiceIO
from jarvis.tts_engine import synthesizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--samples', type=int, default=30)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.samples < 2:
        parser.error('Use pelo menos duas amostras para separar carga fria')
    voice = VoiceIO(piper_model=str(args.model))
    rows = []
    for index in range(args.samples):
        delivered = []
        start = monotonic()
        def sink(argv):
            with wave.open(argv[-1]) as wav:
                frames = wav.getnframes()
                if frames <= 0:
                    raise RuntimeError('WAV vazio')
            delivered.append(monotonic() - start)
        voice._run_audio = sink
        voice.prepare_speech()
        voice.speak('A primeira frase está pronta. A segunda frase preserva a ordem.')
        if len(delivered) != 2:
            raise RuntimeError('Ordem ou número de frases inesperado')
        rows.append({'cold': index == 0, 'first_wav_s': delivered[0],
                     'total_s': monotonic() - start, 'main_rss_kib': rss_kib()})
    result = {'kind': 'real_piper_wav_sink',
              'model_sha256': hashlib.sha256(voice.piper_model.read_bytes()).hexdigest(),
              'samples': args.samples, 'cold': rows[0],
              'warm_first_wav_s': summary([row['first_wav_s'] for row in rows[1:]]),
              'warm_total_s': summary([row['total_s'] for row in rows[1:]]), 'measurements': rows,
              'physical_playback': 'pending', 'limits': 'Sink lê WAV, sem áudio audível nem atraso Bluetooth. RSS principal não inclui worker Piper.'}
    synthesizer.close()
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(output)
    print(json.dumps({key: value for key, value in result.items() if key != 'measurements'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
