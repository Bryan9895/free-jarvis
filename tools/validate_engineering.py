"""Directed engineering acceptance. Fixture inference is controlled unless --fcc."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import zipfile

from jarvis.agent import Agent
from jarvis.approval import ApprovalPolicy
from jarvis.config import Config
from jarvis.memory import Memory
from jarvis.plan_store import PlanStore
from jarvis.planner import TaskPlanner
from jarvis.service import JarvisService
from jarvis.tools import Toolkit

STEPS = ['Clone o projeto dirigido e verifique a revisão.',
         'Instale a dependência local em ambiente isolado e verifique.',
         'Configure o projeto preservando o campo keep.',
         'Execute os testes e verifique a saída e os arquivos.',
         'Inicie o serviço do projeto e verifique seu health.']
CONFIG = '{"keep": "preserved", "enabled": true}\n'


def digest(value):
    return hashlib.sha256(value).hexdigest()


class Fixture:
    def __init__(self, root, *, create=False):
        self.root = Path(root).resolve()
        self.project = self.root / 'project'
        self.source = self.root / 'source'
        self.cache = self.root / 'wheelhouse'
        self.database = self.root / 'state.sqlite3'
        if create:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=False)
            self.cache.mkdir()
            wheel = self.cache / 'jarvis_fixture_dep-1.0.0-py3-none-any.whl'
            files = {'jarvis_fixture_dep/__init__.py': 'VALUE = 17\n',
                'jarvis_fixture_dep-1.0.0.dist-info/METADATA': 'Metadata-Version: 2.1\nName: jarvis-fixture-dep\nVersion: 1.0.0\n',
                'jarvis_fixture_dep-1.0.0.dist-info/WHEEL': 'Wheel-Version: 1.0\nGenerator: jarvis-fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
            files['jarvis_fixture_dep-1.0.0.dist-info/RECORD'] = ''.join(name + ',,\n' for name in files)
            with zipfile.ZipFile(wheel, 'w') as archive:
                for name, value in files.items():
                    entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                    archive.writestr(entry, value)
            shutil.copytree(Path(__file__).resolve().parents[1] / 'tests/fixtures/engineering_project', self.source,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (self.source / 'requirements.txt').write_text('jarvis-fixture-dep==1.0.0 --hash=sha256:' + digest(wheel.read_bytes()) + '\n')
            self.git('init', '-q', str(self.source))
            self.git('-C', str(self.source), 'add', '.')
            self.git('-C', str(self.source), '-c', 'user.name=Jarvis Fixture', '-c',
                     'user.email=fixture@example.invalid', 'commit', '-qm', 'Directed engineering fixture')
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                port = reservation.getsockname()[1]
            data = {'revision': self.git('-C', str(self.source), 'rev-parse', 'HEAD'), 'port': port}
            descriptor = os.open(self.root / 'fixture.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(data, stream)
        self.data = json.loads((self.root / 'fixture.json').read_text())
        self.revision = self.data['revision']
        self.health = f"http://127.0.0.1:{self.data['port']}/health"

    @staticmethod
    def git(*args):
        return subprocess.check_output(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', *args],
            stderr=subprocess.DEVNULL, env={'PATH': '/usr/bin:/bin', 'GIT_CONFIG_GLOBAL': '/dev/null',
                                          'GIT_CONFIG_NOSYSTEM': '1'}).decode().strip()

    def commands(self, *, fail_tests=False):
        checkpoint = {'project': str(self.project), 'revision': self.revision}
        installed = {**checkpoint, 'distributions': ['jarvis-fixture-dep'], 'files': [
            {'path': str(self.project / 'install-count.txt'), 'sha256': digest(b'1\n')}]}
        test_files = [{'path': str(self.project / name), 'sha256': digest((self.source / name).read_bytes())}
                      for name in ('test_suite.py', 'server.py')]
        test_files.append({'path': str(self.project / 'config.json'), 'sha256': digest(CONFIG.encode())})
        python = str(self.project / '.venv/bin/python')
        return [
            ('execute_process', {'argv': ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', 'clone',
                '--no-hardlinks', '--', str(self.source), str(self.project)], 'cwd': str(self.root), 'postconditions': checkpoint}),
            ('execute_process', {'argv': [sys.executable, str(self.project / 'prepare.py'), str(self.cache)],
                'cwd': str(self.project), 'timeout': 120, 'postconditions': installed}),
            ('write_file', {'path': str(self.project / 'config.json'), 'content': CONFIG,
                'expected_sha256': digest((self.source / 'config.json').read_bytes())}),
            ('execute_process', {'argv': [python, str(self.project / 'test_suite.py')] + (['--fail'] if fail_tests else []),
                'cwd': str(self.project), 'postconditions': {**installed, 'files': installed['files'] + test_files,
                    'stdout_sha256': digest(b'ENGINEERING_TESTS_OK\n')}}),
            ('project_service', {'action': 'start', 'name': 'engineering-fixture', 'cwd': str(self.project),
                'argv': [python, str(self.project / 'server.py'), str(self.data['port'])], 'health': self.health})]


class ControlledProvider:
    active_model = 'controlled-engineering-fixture'

    def __init__(self, fixture, *, fail_tests=False):
        self.commands = fixture.commands(fail_tests=fail_tests)
        self.tool_requests = []

    def responses(self, payload):
        if payload.get('tools') == []:
            return {'output_text': json.dumps({'steps': [
                {'description': description, 'depends_on': [index] if index else []}
                for index, description in enumerate(STEPS)]})}
        items = payload['input']
        index = max(i for i, item in enumerate(items) if item.get('role') == 'user')
        if any(item.get('type') == 'function_call_output' for item in items[index + 1:]):
            return {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Etapa dirigida processada.'}]}]}
        step = STEPS.index(items[index]['content'])
        name, arguments = self.commands[step]
        self.tool_requests.append(name)
        return {'output': [{'type': 'function_call', 'name': name, 'call_id': f'fixture-{step}',
                            'arguments': json.dumps(arguments)}]}


def make_service(fixture, *, fcc=False, fail_tests=False):
    if fcc:
        from dataclasses import replace
        from jarvis.provider_factory import create_provider
        from jarvis.cli import confirm
        provider = create_provider(replace(Config.from_env(), profile='fcc'))
        approval = ApprovalPolicy(auto=False, manual_callback=confirm, report=lambda _: None)
    else:
        provider = ControlledProvider(fixture, fail_tests=fail_tests)
        # In-memory approvals for fixed fixture calls only, never persisted grants.
        approval = ApprovalPolicy(auto=False, manual_callback=lambda _: True, report=lambda _: None)
    toolkit = Toolkit(fixture.root, approve=approval, layout_db=fixture.database,
        enabled_capabilities={'filesystem.read', 'filesystem.write', 'command.read', 'command.execute'})
    toolkit.allowed_roots = [fixture.root]
    memory = Memory(fixture.database)
    agent = Agent(provider, toolkit, memory, provider.active_model)
    planner = TaskPlanner(provider, agent, PlanStore(fixture.database))
    return JarvisService(provider, agent, toolkit, memory, planner, approval, report=lambda _: None)


def prepare(service, fixture):
    goal = (f'No workspace {fixture.root}: clone source em project na revisão {fixture.revision}. '
        'Execute project/prepare.py com wheelhouse; preserve keep e habilite enabled no config.json. '
        f'Rode test_suite.py e inicie server.py na porta {fixture.data["port"]}. '
        'Use pós-condições explícitas para conferir cada processo e health antes de confirmar.')
    service.planner.prepare(goal)


def report(service, fixture, *, fcc=False):
    plan = service.planner.snapshot()
    status = service.toolkit.project_service('status', 'engineering-fixture', str(fixture.project))
    checkpoint = service.toolkit.project_checkpoint(str(fixture.project)) if fixture.project.is_dir() else {}
    config = json.loads((fixture.project / 'config.json').read_text()) if fixture.project.is_dir() else {}
    return {'kind': 'fcc_engineering_journey' if fcc else 'controlled_engineering_journey',
        'plan_state': plan['status'], 'steps': [step['status'] for step in plan.get('steps', [])],
        'expected_revision': fixture.revision, 'revision_matches': checkpoint.get('revision') == fixture.revision,
        'configuration_preserved': config.get('keep') == 'preserved',
        'install_count': int((fixture.project / 'install-count.txt').read_text()) if (fixture.project / 'install-count.txt').is_file() else 0,
        'health_verified': bool(status.get('effect_verified')), 'service_identity': status.get('identity'),
        'external_network_isolation': 'Não testado', 'physical_audio': 'Não testado',
        'limits': ('FCC real; roteamento e isolamento externo exigem comprovação separada. ' if fcc else
                   'Provedor controlado não comprova interpretação FCC. ') +
                  'Clone, venv, wheel local, testes e HTTP são operações reais.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True, help='Novo diretório privado; --resume reutiliza fixture existente')
    parser.add_argument('--fcc', action='store_true', help='FCC real, com aprovações interativas; pode consumir cota')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--resolve', choices=('retry', 'skip'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.resolve and not args.resume:
        parser.error('--resolve exige --resume')
    fixture = Fixture(args.directory, create=not args.resume)
    service = make_service(fixture, fcc=args.fcc)
    try:
        if not args.resume:
            prepare(service, fixture)
        else:
            if args.resolve: service.planner.resolve_step(args.resolve)
            service.planner.ready_to_resume()
        service.plan_action('execute')
        result = report(service, fixture, fcc=args.fcc)
    finally:
        cleanup = True
        try:
            if fixture.project.is_dir():
                observed = service.toolkit.project_service('status', 'engineering-fixture', str(fixture.project))
                if observed.get('running'):
                    stopped = service.toolkit.project_service('stop', 'engineering-fixture', str(fixture.project))
                    cleanup = bool(stopped.get('stopped'))
        finally:
            service.close()
    result['service_stopped_after_probe'] = cleanup
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['plan_state'] != 'completed_verified' or not cleanup:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
