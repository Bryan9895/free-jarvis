"""Processos com saída limitada, cancelamento do grupo e autenticação nativa."""
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
from time import monotonic

from .cancellation import CancelledError
from .filesystem_tools import ToolError


def limited_process(argv, cwd, *, token=None, timeout=60, revoked=lambda: False):
    env = {key: os.environ[key] for key in ('LANG', 'DISPLAY', 'WAYLAND_DISPLAY',
            'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS') if key in os.environ}
    env.update(PATH='/usr/local/bin:/usr/bin:/bin', LC_ALL='C.UTF-8', HOME=str(Path.home()))
    output = {'stdout': bytearray(), 'stderr': bytearray()}
    truncated = False
    process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.DEVNULL, start_new_session=True, env=env)
    deadline = monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            for name, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                if token is not None:
                    token.check()
                if revoked():
                    raise CancelledError('Autorização revogada; processo interrompido')
                if monotonic() >= deadline:
                    raise TimeoutError('Tempo limite do processo; efeitos anteriores podem ter ocorrido')
                for key, _ in selector.select(.05):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        room = max(0, 32768 - len(output[key.data]))
                        output[key.data].extend(chunk[:room])
                        truncated |= len(chunk) > room
            code = process.wait(timeout=max(.001, deadline - monotonic()))
        return {'status': 'executed' if code == 0 else 'failed', 'exit_code': code,
                **{key: value.decode('utf-8', errors='replace') for key, value in output.items()},
                'output_truncated': truncated,
                'effect_verified': False}
    finally:
        # Também recolher descendentes que herdaram o grupo, sem manter daemons
        # órfãos após falha, cancelamento ou término de um comando de primeiro plano.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=.3)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Processo privilegiado pode continuar; confira o efeito antes de repetir')
        finally:
            process.stdout.close()
            process.stderr.close()




class CommandTools:
    def execute_process(self, argv, cwd='.', timeout=60):
        if (not isinstance(argv, list) or not argv or len(argv) > 128 or
                not all(isinstance(value, str) and value and '\x00' not in value for value in argv)):
            raise ToolError('argv deve ser uma lista de argumentos válidos')
        if type(timeout) not in (int, float) or not 1 <= timeout <= 300:
            raise ToolError('Timeout deve estar entre 1 e 300 segundos')
        directory = self.path(cwd)
        authorize = getattr(self.approve, 'authorize', None)
        if authorize is None or not authorize('terminal', 'EXECUTAR PROCESSO: ' + repr(argv)[:2000]):
            return {'status': 'rejected'}
        # Código arbitrário executado como o usuário pode ler dados da conta.
        # Não prometer um isolamento de segredos baseado em nomes de arquivos.
        if not self.approve.granted('secrets') and not authorize('secrets',
                'EXECUTAR CÓDIGO COM ACESSO AOS DADOS DA CONTA, inclusive dados sensíveis: ' + repr(argv)[:1500]):
            return {'status': 'rejected'}
        command = argv
        self._check_execution()
        return limited_process(command, directory, token=self._execution_token, timeout=timeout,
                               revoked=lambda: getattr(self.approve, 'mode', None) == 'revoked')

    def _check_execution(self):
        if self._execution_token is not None:
            self._execution_token.check()
        if getattr(self.approve, 'mode', None) == 'revoked':
            raise CancelledError('Sessão revogada')

    def manage_packages(self, action, packages):
        if action not in ('install', 'remove') or not packages or not all(
                re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?', p) for p in packages):
            raise ToolError('Pacotes inválidos')
        authorize = getattr(self.approve, 'authorize', None)
        if authorize is None or not authorize('administration', f'ADMINISTRAÇÃO: apt-get {action} ' + ' '.join(packages)):
            return {'status': 'rejected'}
        if not shutil.which('pkexec') or not shutil.which('apt-get'):
            return {'status': 'unavailable', 'reason': 'pkexec/apt-get indisponível'}
        self._check_execution()
        result = limited_process(['/usr/bin/pkexec', '/usr/bin/apt-get', '-y', action, '--', *packages],
            self.workspace, token=self._execution_token, timeout=300,
            revoked=lambda: self.approve.mode == 'revoked')
        # dpkg-query confirma o estado dos pacotes; saída do apt sozinha não basta.
        statuses = []
        for package in packages:
            self._check_execution()
            observed = limited_process(['/usr/bin/dpkg-query', '-W', '-f=${Status}', package],
                self.workspace, token=self._execution_token, timeout=10)
            statuses.append(observed['stdout'].strip() == 'install ok installed')
        verified = all(statuses) if action == 'install' else not any(statuses)
        result['effect_verified'] = result['exit_code'] == 0 and verified
        if result['effect_verified']:
            result['status'] = 'verified'
        result['packages'] = dict(zip(packages, statuses))
        return result

    def manage_service(self, action, unit):
        if action not in ('start', 'stop', 'restart') or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]*\.service', unit):
            raise ToolError('Serviço/ação inválidos')
        authorize = getattr(self.approve, 'authorize', None)
        if authorize is None or not authorize('administration', f'ADMINISTRAÇÃO: systemctl {action} {unit}'):
            return {'status': 'rejected'}
        if not shutil.which('pkexec') or not shutil.which('systemctl'):
            return {'status': 'unavailable'}
        self._check_execution()
        result = limited_process(['/usr/bin/pkexec', '/usr/bin/systemctl', action, '--', unit],
            self.workspace, token=self._execution_token, timeout=120,
            revoked=lambda: self.approve.mode == 'revoked')
        self._check_execution()
        observation = limited_process(['/usr/bin/systemctl', 'show', '--property=ActiveState', '--value', '--', unit],
            self.workspace, token=self._execution_token, timeout=10)
        state = observation['stdout'].strip()
        verified = state == 'inactive' if action == 'stop' else state == 'active'
        result.update(active_state=state, effect_verified=result['exit_code'] == 0 and verified and observation['exit_code'] == 0)
        if result['effect_verified']:
            result['status'] = 'verified'
        return result
