"""Benchmark de jornadas textuais; relatórios não contêm prompts nem respostas."""
import argparse
import json
from pathlib import Path
import resource
import tempfile
from time import monotonic, process_time, sleep

from .agent import Agent
from .approval import ApprovalPolicy
from .cancellation import CancelledError
from .conversation import ConversationController
from .fcc import FCCClient, AutoModelClient, FCCError
from .latency import summary
from .memory import Memory
from .planner import TaskPlanner
from .service import JarvisService
from .tools import Toolkit


SCENARIOS = (
    ('short_question', 'O que é uma rede neural?'),
    ('long_answer', 'Explique o conceito de aprendizado de máquina.'),
    ('simple_action', 'Adicione às tarefas: revisar relatório.'),
    ('compound_action', 'Adicione preparar relatório às tarefas e crie o arquivo resultado.txt com teste.'),
    ('network_failure', 'O que é fotossíntese?'),
    ('voice_failure', 'O que significa CPU?'),
    ('cancel', 'O que é uma estrela?'),
)


class ControlledProvider:
    active_model = 'controlled-fixture'
    scenario = ''

    def responses(self, payload):
        return self.stream_responses(payload)

    def stream_responses(self, payload, *, on_event=None, cancel_token=None, **_):
        sleep(.005)
        if self.scenario == 'network_failure':
            raise FCCError('Falha de rede controlada')
        if self.scenario == 'cancel':
            cancel_token.cancel()
            cancel_token.check()
        completed = any(item.get('type') == 'function_call_output' for item in payload['input'])
        if not completed and self.scenario in ('simple_action', 'compound_action'):
            output = [{'type': 'function_call', 'name': 'task_add', 'call_id': 'task',
                       'arguments': json.dumps({'title': 'preparar relatório' if self.scenario == 'compound_action' else 'revisar relatório'})}]
            if self.scenario == 'compound_action':
                output.append({'type': 'function_call', 'name': 'write_file', 'call_id': 'file',
                               'arguments': json.dumps({'path': 'resultado.txt', 'content': 'teste'})})
            return {'output': output}
        text = 'Resposta controlada. ' * (30 if self.scenario == 'long_answer' else 1)
        text = text.strip()
        if not payload.get('tools') and on_event is not None:
            for start in range(0, len(text), 20):
                on_event({'type': 'response.output_text.delta', 'delta': text[start:start + 20]})
        return {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]}


def rss_kib():
    try:
        import os
        return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE') // 1024
    except OSError:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def _baseline_classes(directory):
    import importlib.util
    import importlib
    import sys
    directory = Path(directory)
    name = '_jarvis_benchmark_baseline'
    spec = importlib.util.spec_from_file_location(name, directory / '__init__.py',
                                                 submodule_search_locations=[str(directory)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    spec.loader.exec_module(package)
    return {symbol: getattr(importlib.import_module(name + '.' + module), symbol)
            for module, symbol in (('fcc', 'FCCClient'), ('fcc', 'AutoModelClient'), ('fcc', 'FCCError'),
                ('cancellation', 'CancelledError'),
                ('agent', 'Agent'), ('approval', 'ApprovalPolicy'), ('memory', 'Memory'),
                ('tools', 'Toolkit'), ('planner', 'TaskPlanner'), ('service', 'JarvisService'),
                ('conversation', 'ConversationController'))}


def measure(samples=30, *, real_fcc=False, baseline_package=None, scenario=None):
    classes = _baseline_classes(baseline_package) if baseline_package else globals()

    provider = ControlledProvider()
    if real_fcc:
        from .config import Config
        import os
        config = Config.from_env()
        provider = classes['AutoModelClient'](classes['FCCClient'](config.url, config.token), preferred=config.model,
            backups=tuple(x for x in os.getenv('FCC_FALLBACK_MODELS', '').split(',') if x),
            allow_cross_provider=os.getenv('FCC_ALLOW_CROSS_PROVIDER') == '1')
        provider.initialize()
    rows = []
    with tempfile.TemporaryDirectory(prefix='jarvis-benchmark-') as td:
        root = Path(td)
        memory = classes['Memory'](root / 'metrics.db')
        approval = classes['ApprovalPolicy'](report=lambda _: None)
        toolkit = classes['Toolkit'](root, approve=approval, layout_db=root / 'metrics.db',
            enabled_capabilities={'filesystem.read', 'filesystem.write', 'tasks.read', 'tasks.write'})
        toolkit.allowed_roots = [root]
        agent = classes['Agent'](provider, toolkit, memory, provider.active_model)
        service = classes['JarvisService'](provider, agent, toolkit, memory, classes['TaskPlanner'](provider, agent), approval, report=lambda _: None)
        events = []
        controller = classes['ConversationController'](service, emit=events.append)
        try:
            for index in range(samples):
                scenarios = SCENARIOS[:4] if real_fcc else SCENARIOS
                if scenario is not None:
                    scenarios = tuple(item for item in scenarios if item[0] == scenario)
                    if not scenarios:
                        raise ValueError('Cenário indisponível neste modo')
                name, message = scenarios[index % len(scenarios)]
                expected_title = 'revisar relatório' if name == 'simple_action' else 'preparar relatório'
                filename = 'resultado.txt'
                if real_fcc and name in ('simple_action', 'compound_action'):
                    expected_title += ' ' + str(index + 1)
                    message = 'Adicione às tarefas: ' + expected_title + '.'
                    if name == 'compound_action':
                        filename = f'resultado-{index + 1}.txt'
                        message += f' E crie o arquivo {filename} com o conteúdo teste.'
                task_ids = {item['id'] for item in toolkit.task_list()['tasks']}
                target = root / filename
                if target.is_file():
                    target.unlink()
                operation_count = len(toolkit.operation_log)
                if not real_fcc:
                    provider.scenario = name
                first = []
                events.clear()
                started, cpu = monotonic(), process_time()
                def visible(_):
                    if not first:
                        first.append(monotonic() - started)
                voice = None
                if name == 'voice_failure':
                    class FailedVoice:
                        def prepare_speech(self): pass
                        def cancel_speech(self): pass
                        def speak(self, _): raise RuntimeError('Falha TTS controlada')
                    voice = FailedVoice()
                state = 'passed'
                error_category, error_status = None, None
                try:
                    if baseline_package:
                        controller.run(message, voice=voice, display=visible)
                    else:
                        controller.run(message, voice=voice, on_text=visible, display=visible)
                    if any(event.state == 'erro' for event in events):
                        state = 'failed'
                except (CancelledError, classes['CancelledError']):
                    state = 'cancelled'
                except (FCCError, classes['FCCError'], TimeoutError, ValueError) as exc:
                    state = 'failed'
                    error_category = getattr(exc, 'category', type(exc).__name__)
                    error_status = getattr(exc, 'status', None)
                effect_verified = None
                if name in ('simple_action', 'compound_action'):
                    effect_verified = any(item['id'] not in task_ids and item['title'].strip().casefold() == expected_title
                                          for item in toolkit.task_list()['tasks'])
                    if name == 'compound_action':
                        effect_verified = (effect_verified and target.is_file() and
                                           target.read_text().strip() == 'teste')
                    if not effect_verified:
                        state = 'failed'
                trace = (controller.last_trace.snapshot() if not baseline_package else
                         {'events': [{'stage': event.state, 'at': event.at} for event in events]})
                yield {'scenario': name, 'state': state, 'total_s': monotonic() - started,
                       'error_category': error_category, 'error_status': error_status,
                       'first_visual_s': first[0] if first else None,
                       'cpu_s': process_time() - cpu, 'rss_kib': rss_kib(),
                       'model': getattr(provider, 'active_model', ''),
                       'effect_verified': effect_verified,
                       'model_rounds': agent.last_metrics.get('model_rounds', 0),
                       'tools_executed': len(toolkit.operation_log) - operation_count,
                       'tool_problems': len(agent.last_metrics.get('tool_problems', [])),
                       'trace': trace}
                if error_status == 429:
                    return
        finally:
            service.close()


def report(rows, *, real_fcc=False):
    grouped = {}
    for name in dict.fromkeys(row['scenario'] for row in rows):
        subset = [row for row in rows if row['scenario'] == name]
        grouped[name] = {'total_s': summary([row['total_s'] for row in subset]),
            'first_visual_s': summary([row['first_visual_s'] for row in subset if row['first_visual_s'] is not None]),
            'failures': sum(row['state'] == 'failed' for row in subset),
            'cancelled': sum(row['state'] == 'cancelled' for row in subset)}
    return {'kind': 'fcc_text_journeys' if real_fcc else 'controlled_text_journeys',
            'model': rows[-1]['model'] if rows else '', 'samples': len(rows), 'scenarios': grouped, 'turns': rows,
            'physical_audio': 'pending', 'stt_quality': 'pending',
            'limits': 'Amostras pequenas por classe; p95 descritivo, sem estabilidade estatística. RSS inclui caches. Não mede fim de fala ou som físico.'}


def run(samples=30, *, real_fcc=False, scenario=None):
    result = report(list(measure(samples, real_fcc=real_fcc, scenario=scenario)), real_fcc=real_fcc)
    result.update(expected_samples=samples, completed=result['samples'] == samples)
    return result


def compare(samples, baseline_package, *, checkpoint=None):
    before = measure(samples, real_fcc=True, baseline_package=baseline_package)
    after = measure(samples, real_fcc=True)
    rows = {'before': [], 'after': []}
    stopped = False
    def snapshot():
        return {'kind': 'alternating_fcc_comparison',
                **{kind: report(values, real_fcc=True) for kind, values in rows.items()},
                'expected_samples_per_version': samples,
                'completed': all(len(values) == samples for values in rows.values()),
                'limits': 'Sem áudio físico. Mesmo catálogo/configuração; verificar modelos efetivos, falhas e qualidade antes de atribuir ganhos.'}
    try:
        for index in range(samples):
            order = ('before', 'after') if index % 2 else ('after', 'before')
            for kind in order:
                row = next(before if kind == 'before' else after)
                rows[kind].append(row)
                print(f"{kind} {index + 1}/{samples}: {row['scenario']} {row['state']} {row['total_s']:.3f}s", flush=True)
                if checkpoint:
                    checkpoint(snapshot())
                if row.get('error_status') == 429:
                    stopped = True
                    break
            if stopped:
                break
    finally:
        before.close()
        after.close()
    return snapshot()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=30)
    parser.add_argument('--fcc', action='store_true', help='Usa o modelo configurado e somente arquivos/tarefas temporários')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline-package', type=Path, help='Com --fcc, compara pacote antigo extraído do Git em ordem alternada')
    parser.add_argument('--scenario', choices=tuple(item[0] for item in SCENARIOS))
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('samples deve ser positivo')
    def checkpoint(result):
        if args.output:
            args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    result = compare(args.samples, args.baseline_package, checkpoint=checkpoint) if args.baseline_package and args.fcc else run(args.samples, real_fcc=args.fcc, scenario=args.scenario)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    compact = ({'kind': result['kind'], **{version: {k: v for k, v in result[version].items() if k != 'turns'} for version in ('before', 'after')}}
               if 'before' in result else {key: value for key, value in result.items() if key != 'turns'})
    print(json.dumps(compact, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
