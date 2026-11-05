"""Síntese local real e pipeline; sink WAV sem reprodução física."""
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
from jarvis.kokoro_engine import kokoro_synthesizer
from jarvis.resource_sampling import MemorySampler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, help='Modelo Piper instalado')
    parser.add_argument('--backend', choices=('piper', 'kokoro'), default='piper')
    parser.add_argument('--samples', type=int, default=30)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.samples < 2:
        parser.error('Use pelo menos duas amostras para separar carga fria')
    if args.backend == 'piper' and args.model is None:
        parser.error('--model é obrigatório para Piper')
    voice = VoiceIO(piper_model=str(args.model) if args.model else '')
    voice.tts_backend = args.backend
    synthesizer.close()
    kokoro_synthesizer.close()
    if args.backend == 'kokoro':
        from jarvis.kokoro_assets import verify_assets
        asset_hashes = verify_assets(voice.kokoro_directory)['sha256']
    else:
        asset_hashes = {'piper': hashlib.sha256(voice.piper_model.read_bytes()).hexdigest()}
    rows = []
    with MemorySampler() as sampler:
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
    result = {'kind': 'real_' + args.backend + '_wav_sink',
              'asset_sha256': asset_hashes,
              'memory': sampler.result,
              'samples': args.samples, 'cold': rows[0],
              'warm_first_wav_s': summary([row['first_wav_s'] for row in rows[1:]]),
              'warm_total_s': summary([row['total_s'] for row in rows[1:]]), 'measurements': rows,
              'physical_playback': 'pending', 'limits': 'Sink lê WAV, sem áudio audível nem atraso Bluetooth. RSS principal não inclui worker de voz.'}
    synthesizer.close()
    kokoro_synthesizer.close()
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(output)
    print(json.dumps({key: value for key, value in result.items() if key != 'measurements'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
