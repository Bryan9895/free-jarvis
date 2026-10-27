"""Avalia corpus JSON externo: [{audio, reference, consent: true}]."""
import argparse
import json
from pathlib import Path
from time import monotonic, process_time
from jarvis.latency import summary
from jarvis.stt_evaluation import word_errors, critical_match
from jarvis.voice import VoiceIO, VoiceError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--beams', nargs='+', type=int, choices=(1, 3, 5), default=[5])
    parser.add_argument('--model', choices=('small', 'base', 'tiny'), default='small')
    parser.add_argument('--without-vad', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    records = json.loads(args.corpus.read_text())
    if not isinstance(records, list) or not records or any(
            not isinstance(row, dict) or row.get('consent') is not True
            or not isinstance(row.get('audio'), str) or not isinstance(row.get('reference'), str)
            for row in records):
        parser.error('Cada amostra exige audio, reference e consent=true')
    audio = [(args.corpus.parent / row['audio']).resolve() for row in records]
    if not all(path.is_file() for path in audio):
        parser.error('Há amostras inexistentes; nenhuma inferência foi iniciada')
    voice = VoiceIO(model=args.model)
    profiles = {beam: [] for beam in args.beams}
    cold = True
    for index, (row, path) in enumerate(zip(records, audio)):
        order = args.beams if index % 2 else list(reversed(args.beams))
        for beam in order:
            started, cpu = monotonic(), process_time()
            failed = False
            try:
                text = voice.transcribe(path, beam_size=beam, vad_filter=not args.without_vad)
            except VoiceError:
                text, failed = '', True
            errors, count = word_errors(row['reference'], text)
            profiles[beam].append({'seconds': monotonic() - started, 'cpu_s': process_time() - cpu,
                                  'word_errors': errors, 'reference_words': count,
                                  'critical_match': critical_match(row['reference'], text),
                                  'failed': failed, 'includes_cold_load': cold})
            cold = False
    result = {'kind': 'consented_stt_corpus', 'model': voice.model_name,
              'vad_filter': not args.without_vad, 'audio_or_transcriptions_saved': False, 'profiles': {}}
    for beam, measurements in profiles.items():
        words = sum(row['reference_words'] for row in measurements)
        result['profiles'][beam] = {
            'n': len(measurements),
            'wer': sum(row['word_errors'] for row in measurements) / max(1, words),
            'critical_match_rate': sum(row['critical_match'] for row in measurements) / len(measurements),
            'failures': sum(row['failed'] for row in measurements),
            'warm_seconds': summary([row['seconds'] for row in measurements if not row['includes_cold_load']]),
            'measurements': measurements}
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
