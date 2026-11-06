"""Avalia corpus WAV externo consentido sem capturar áudio ou salvar texto."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import wave

from jarvis.stt_corpus import evaluate, load_corpus, describe, fingerprint
from jarvis.resource_sampling import MemorySampler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--beams', nargs='+', type=int, choices=(1, 3, 5), default=[5])
    parser.add_argument('--model', choices=('small', 'base', 'tiny'), default='small')
    parser.add_argument('--without-vad', action='store_true')
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--preflight', action='store_true', help='Valida consentimento/WAV/cobertura sem carregar Whisper')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        samples = load_corpus(args.corpus)
        if args.output and args.output.resolve() in {args.corpus.resolve(), *(sample['path'] for sample in samples)}:
            raise ValueError('Relatório, manifesto e áudio exigem arquivos distintos')
        if args.preflight:
            result = {'kind': 'consented_stt_corpus_preflight', 'schema_version': 2,
                      'corpus_sha256': fingerprint(args.corpus), **describe(samples),
                      'inference': 'Não testado', 'physical_bluetooth': 'Não testado'}
        else:
            with MemorySampler() as memory:
                result = evaluate(args.corpus, model=args.model, beams=args.beams,
                    repetitions=args.repetitions, vad_filter=not args.without_vad)
            result['memory'] = memory.result
        output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix='.stt-evaluation-', dir=args.output.parent)
            try:
                with os.fdopen(descriptor, 'w') as stream: stream.write(output)
                os.replace(temporary, args.output)
            finally:
                Path(temporary).unlink(missing_ok=True)
        print(output)
    except (ValueError, OSError, EOFError, wave.Error) as exc:
        parser.exit(1, 'Avaliação não concluída (' + type(exc).__name__ + '). Confira consentimento, WAV e manifesto.\n')


if __name__ == '__main__':
    main()
