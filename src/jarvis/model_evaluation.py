"""Private comparison artifacts and explicit quality review, shared by GUI work."""
import json
import os
from pathlib import Path
import tempfile

from .cancellation import CancellationToken, CancelledError
from .model_comparison import compare, select, verify_monitor
from .stt_corpus import outside_git, fingerprint

LIMIT = 64 * 1024 * 1024


def _json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > LIMIT:
        raise ValueError('Arquivo de avaliação excede o limite')
    return json.loads(path.read_text())


def _save(path, value):
    content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if len(content.encode()) > LIMIT:
        raise ValueError('Relatório de avaliação excede o limite')
    descriptor, name = tempfile.mkstemp(prefix='.evaluation-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def load(directory):
    root = Path(directory).expanduser().resolve()
    outside_git(root / '.evaluation-probe')
    report = _json(root / 'metrics.json')
    if report.get('kind') != 'local_cold_warm_comparison':
        raise ValueError('Relatório de comparação inválido')
    responses = root / 'responses.jsonl'
    if responses.is_symlink() or not responses.is_file() or responses.stat().st_size > LIMIT:
        raise ValueError('Arquivo de respostas inválido')
    if report.get('review_output_sha256') != fingerprint(responses):
        raise ValueError('Respostas mudaram após o ensaio')
    return root, report


def evaluate(config, models, *, directory, monitor_pid, cancel_token=None, progress=lambda _: None):
    from .local_provider import local_model
    models = list(dict.fromkeys(local_model(model) for model in models))
    if len(models) != 2:
        raise ValueError('Informe dois modelos distintos')
    token = cancel_token or CancellationToken()
    token.check()
    verify_monitor(config, [monitor_pid])
    parent = Path(directory).expanduser().resolve()
    outside_git(parent / '.evaluation-probe')
    if not parent.is_dir():
        raise ValueError('Escolha uma pasta existente fora de Git')
    root = Path(tempfile.mkdtemp(prefix='jarvis-models-', dir=parent))
    progress({'directory': str(root), 'state': 'created'})
    report = {'kind': 'local_cold_warm_comparison', 'models': {}, 'completed': False,
              'state': 'running', 'selected_model': None, 'defaults_changed': False}
    responses = root / 'responses.jsonl'
    count = 0
    def checkpoint(value):
        nonlocal report
        report = value
        _save(root / 'metrics.json', value)
    descriptor = os.open(responses, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        def record(row):
            nonlocal count
            if any(not isinstance(row.get(key), str) or len(row[key]) > 65536 for key in ('request', 'answer')):
                raise ValueError('Resposta dirigida excede o limite de revisão')
            content = json.dumps({**row, 'ordinal': count}, ensure_ascii=False) + '\n'
            if stream.tell() + len(content.encode()) > LIMIT:
                raise ValueError('Arquivo de respostas excede o limite')
            stream.write(content)
            stream.flush()
            count += 1
        try:
            checkpoint(report)
            compare(models, monitor_pids=[monitor_pid], config=config, cancel_token=token,
                    checkpoint=checkpoint, review_sink=record, progress=progress)
        except (CancelledError, KeyboardInterrupt):
            report.update(state='cancelled', completed=False, selected_model=None)
        except Exception as exc:
            report.update(state='failed', completed=False, selected_model=None, error_category=type(exc).__name__)
        finally:
            stream.flush()
            report['review_output_sha256'] = fingerprint(responses)
            checkpoint(report)
    return root, report


def responses_for_review(directory):
    root, report = load(directory)
    path = root / 'responses.jsonl'
    if path.stat().st_size > LIMIT:
        raise ValueError('Respostas excedem o limite')
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if len(rows) > 1000 or any(not isinstance(row, dict) or row.get('ordinal') != index
            or row.get('model') not in report['models'] or row.get('phase') not in ('cold', 'warm')
            or row.get('state') not in ('passed', 'failed', 'cancelled')
            or any(not isinstance(row.get(key), str) or len(row[key]) > 65536
                   for key in ('request', 'answer', 'scenario')) for index, row in enumerate(rows)):
        raise ValueError('Arquivo de respostas com esquema inválido')
    if fingerprint(path) != report['review_output_sha256']:
        raise ValueError('Respostas mudaram durante a leitura')
    return rows


def review(directory, assessments):
    root, report = load(directory)
    sha = fingerprint(root / 'metrics.json')
    if report.get('state') != 'completed' or not report.get('completed') or len(report['models']) != 2:
        raise ValueError('Conclua os dois modelos antes da revisão de seleção')
    if not isinstance(assessments, dict) or set(assessments) != set(report['models']):
        raise ValueError('Revisão exige os dois modelos exatos do relatório')
    rows = responses_for_review(root)
    reviews = {}
    for model, data in report['models'].items():
        entry = assessments[model]
        fields = {'reviewed', 'adequate', 'critical_errors', 'oom'}
        if not isinstance(entry, dict) or set(entry) != fields or any(type(entry[key]) is not int or entry[key] < 0 for key in fields):
            raise ValueError('Informe contagens inteiras não negativas na revisão')
        turns = [turn for run in data['runs'] for turn in run['turns']]
        expected = len(turns)
        archived = [row for row in rows if row['model'] == model]
        if (not data.get('completed') or not data.get('unloaded') or not expected
                or len(archived) != expected or entry['reviewed'] != expected
                or entry['adequate'] > expected or entry['critical_errors'] > expected):
            raise ValueError('Revise todas as respostas arquivadas de cada modelo')
        reviews[model] = {'quality_rate': entry['adequate'] / expected,
            'critical_rate': 1 - entry['critical_errors'] / expected, 'reviewed_turns': expected,
            'oom': entry['oom'], 'wrong_effects': sum(bool(turn.get('wrong_effect')) for turn in turns),
            'duplicate_effects': sum(bool(turn.get('duplicate_effect')) for turn in turns)}
    quality = {'report_sha256': sha, 'models': reviews, 'assessments': assessments,
               'review_output_sha256': report['review_output_sha256'], 'quality_source': 'human_declared'}
    selected = select(report['models'], reviews)
    if fingerprint(root / 'metrics.json') != sha or fingerprint(root / 'responses.jsonl') != report['review_output_sha256']:
        raise ValueError('Arquivos mudaram durante a revisão')
    _save(root / 'quality.json', quality)
    selection = {'report_sha256': sha, 'quality_sha256': fingerprint(root / 'quality.json'),
                 'selected_model': selected, 'defaults_changed': False,
                 'selection': 'Modelo elegível; aplicação exige ação explícita' if selected else 'Nenhum modelo elegível'}
    _save(root / 'selection.json', selection)
    return selection


def approved_model(directory):
    root, report = load(directory)
    selection, quality = _json(root / 'selection.json'), _json(root / 'quality.json')
    sha = fingerprint(root / 'metrics.json')
    if (report.get('state') != 'completed' or not report.get('completed')
            or selection.get('report_sha256') != sha or quality.get('report_sha256') != sha
            or selection.get('quality_sha256') != fingerprint(root / 'quality.json')
            or quality.get('review_output_sha256') != report['review_output_sha256']):
        raise ValueError('Revisão e seleção não correspondem a estes arquivos')
    model = select(report['models'], quality['models'])
    if not model or model != selection.get('selected_model'):
        raise ValueError('Nenhum modelo elegível nesta revisão')
    return model, report['models'][model]['identity']
