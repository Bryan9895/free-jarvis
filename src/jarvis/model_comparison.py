"""Explicit real Local comparison: three unloaded and thirty warm turns per case."""
import argparse
import json
import math
import hashlib
import os
from pathlib import Path
import tempfile

from .benchmark import run, SCENARIOS
from .config import Config
from .local_provider import OpenJarvisProvider, local_model
from .latency import summary


def startup_share(entry):
    shares = []
    for turn in entry['turns']:
        events = turn.get('trace', {}).get('events', [])
        start = next((event['at'] for event in events if event['stage'] == 'local_worker_start'), None)
        ready = next((event['at'] for event in events if event['stage'] == 'local_worker_ready'), None)
        first = turn.get('first_visual_s')
        if start is not None and ready is not None and first and ready >= start:
            shares.append((ready - start) / first)
    measured = summary(shares)
    return {'first_worker_over_first_visual': measured,
            'resident_optimization': 'Investigar: mediana acima de 10%' if measured['p50'] is not None
                and measured['p50'] > .1 else 'Não justificada por esta amostra'}


def select(results, reviews):
    eligible = []
    for model, data in results.items():
        review = reviews.get(model, {})
        turns = [turn for entry in data['runs'] for turn in entry['turns']]
        warm = [entry for entry in data['runs'] if entry['phase'] == 'warm']
        values = [entry['scenarios'][entry['scenario']]['first_visual_s']['p95'] for entry in warm]
        if (not data.get('completed') or not warm or any(value is None for value in values)
                or not turns or any(turn['state'] != 'passed' or turn.get('wrong_effect')
                                    or turn.get('duplicate_effect') for turn in turns)):
            continue
        quality = review.get('quality_rate')
        if (type(quality) not in (int, float) or not math.isfinite(quality) or not .95 <= quality <= 1
                or review.get('critical_rate') != 1 or review.get('reviewed_turns') != len(turns)
                or any(review.get(key) != 0 for key in ('oom', 'wrong_effects', 'duplicate_effects'))):
            continue
        if any(not entry['memory'].get('pss_complete') or entry['memory'].get('missing_root_pids') for entry in warm):
            continue
        pss = max((entry['memory'].get('peak_tree_pss_kib') or float('inf') for entry in warm), default=float('inf'))
        eligible.append((max(values), pss, model))
    return min(eligible)[2] if eligible else None


def compare(models, *, monitor_pids, reviews=None, checkpoint=lambda _: None, review_sink=None):
    models = list(dict.fromkeys(local_model(model) for model in models))
    config = Config.from_env()
    results = {}
    report = {'kind': 'local_cold_warm_comparison', 'models': results, 'selected_model': None,
        'selection': 'Pendente: medições completas, revisão de qualidade/negativas e números',
        'physical_audio': 'Não testado', 'network_isolation': 'Não testado',
        'defaults_changed': False, 'cold_runs': 3, 'warm_runs': 30,
        'limits': 'Frio significa pesos descarregados do Ollama; cache de disco do SO não é limpo. '
                  'Primeiro texto é visual, não som no fone. Revisão externa é obrigatória.'}
    previous = os.environ.get('JARVIS_LOCAL_MODEL')
    try:
        for model in models:
            local_model(model)
            os.environ['JARVIS_LOCAL_MODEL'] = model
            provider = OpenJarvisProvider(model=model, host=config.ollama_host, python=config.openjarvis_python)
            provider.initialize()
            data = results[model] = {'identity': provider._exchange({'operation': 'identity', 'model': model}),
                                    'runs': [], 'completed': False}
            scenarios = [item for item in SCENARIOS if item[0] not in ('network_failure', 'voice_failure', 'cancel')]
            for scenario, _ in scenarios:
                for _ in range(3):
                    provider._exchange({'operation': 'unload', 'model': model})
                    entry = run(1, real_local=True, scenario=scenario, monitor_pids=monitor_pids,
                        review_sink=(lambda row: review_sink({**row, 'phase': 'cold'})) if review_sink else None)
                    entry.update(phase='cold', scenario=scenario)
                    data['runs'].append(entry)
                    checkpoint(report)
                    if not entry['completed']:
                        raise RuntimeError('Comparação incompleta')
                # Last cold sample warmed this same model; no unload before thirty warm turns.
                entry = run(30, real_local=True, scenario=scenario, monitor_pids=monitor_pids,
                    review_sink=(lambda row: review_sink({**row, 'phase': 'warm'})) if review_sink else None)
                entry.update(phase='warm', scenario=scenario)
                entry['startup_analysis'] = startup_share(entry)
                data['runs'].append(entry)
                checkpoint(report)
                if not entry['completed']:
                    raise RuntimeError('Comparação incompleta')
            data['completed'] = True
        report['selected_model'] = select(results, reviews or {})
        if report['selected_model']:
            report['selection'] = 'Elegível por revisão fornecida; preferência não alterada'
        checkpoint(report)
        return report
    finally:
        if previous is None: os.environ.pop('JARVIS_LOCAL_MODEL', None)
        else: os.environ['JARVIS_LOCAL_MODEL'] = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', action='append', default=[])
    parser.add_argument('--monitor-pid', type=int, action='append', default=[], help='PID real do daemon Ollama')
    parser.add_argument('--results', type=Path, help='Selecionar a partir de medições já concluídas, sem novas inferências')
    parser.add_argument('--quality-review', type=Path)
    parser.add_argument('--review-output', type=Path, help='Novas respostas de teste para revisão; arquivo privado fora do Git')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.results:
        if not args.quality_review or args.model or args.monitor_pid or args.review_output:
            parser.error('--results exige --quality-review e não executa novos ensaios')
        raw = args.results.read_bytes()
        result = json.loads(raw)
        review = json.loads(args.quality_review.read_text())
        if result.get('kind') != 'local_cold_warm_comparison' or review.get('report_sha256') != hashlib.sha256(raw).hexdigest():
            parser.error('Revisão não corresponde ao SHA256 deste relatório')
        result['selected_model'] = select(result['models'], review['models'])
        result['selection'] = 'Elegível por revisão fornecida; preferência não alterada' if result['selected_model'] else 'Nenhum modelo elegível'
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'selected_model': result['selected_model'], 'selection': result['selection']}, ensure_ascii=False))
        return
    if len(set(args.model)) < 2 or not args.monitor_pid or args.quality_review:
        parser.error('Compare pelo menos dois modelos com --monitor-pid; revise depois usando --results')
    if any(pid < 1 or not Path(f'/proc/{pid}').exists() for pid in args.monitor_pid):
        parser.error('Informe PID vivo para medição de RAM do daemon')
    review_file = None
    if args.review_output:
        target = args.review_output.expanduser().resolve()
        if target == args.output.expanduser().resolve():
            parser.error('Respostas privadas e métricas exigem arquivos distintos')
        if any((parent / '.git').exists() for parent in target.parents):
            parser.error('--review-output precisa ficar fora de repositórios Git')
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        review_file = os.fdopen(descriptor, 'w')
        args.review_output = target
    def record(row):
        review_file.write(json.dumps(row, ensure_ascii=False) + '\n')
        review_file.flush()
    def save(result):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.comparison-', dir=args.output.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, args.output)
        finally:
            Path(temporary).unlink(missing_ok=True)
    try:
        result = compare(args.model, monitor_pids=args.monitor_pid, checkpoint=save,
                         review_sink=record if review_file else None)
        if review_file:
            review_file.flush()
            result['review_output_sha256'] = hashlib.sha256(args.review_output.read_bytes()).hexdigest()
            save(result)
    except (RuntimeError, OSError, ValueError) as exc:
        parser.exit(1, 'Comparação não concluída: ' + type(exc).__name__ + '. Nenhum modelo foi selecionado.\n')
    finally:
        if review_file: review_file.close()
    print(json.dumps({'selected_model': result['selected_model'], 'selection': result['selection']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
