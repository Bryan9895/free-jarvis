"""GUI-owned Ollama session. Existing servers are observed, never terminated."""
import json
import os
import signal
import subprocess
from threading import Event, RLock
from time import monotonic
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler

from .cancellation import CancellationToken
from .local_provider import local_host


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('Servidor local respondeu com redirecionamento')


def _version(host):
    try:
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        with opener.open(host + '/api/version', timeout=.5) as response:
            data = json.loads(response.read(65537))
        version = data.get('version')
        if not isinstance(version, str) or not version or len(version) > 80:
            raise ValueError('Resposta de versão inválida no servidor local')
        return version
    except (URLError, OSError):
        return ''


class OllamaSession:
    def __init__(self):
        self._process = None
        self._host = ''
        self._lock = RLock()

    def monitor_pid(self, host):
        from .project_services import owns_health_port
        with self._lock:
            if (self._process is not None and self._host == local_host(host)
                    and self._process.poll() is None and owns_health_port(self._process.pid, host)):
                return self._process.pid
        return None

    def start(self, host, *, token=None):
        from .ollama_setup import binary, server_environment
        from .project_services import owns_health_port
        token = token or CancellationToken()
        host = local_host(host)
        with self._lock:
            token.check()
            if self._process is not None:
                if self._process.poll() is None:
                    if host != self._host:
                        raise ValueError('Pare o servidor desta janela antes de mudar o endereço')
                    if owns_health_port(self._process.pid, host):
                        version = _version(host)
                        token.check()
                        if version:
                            return {'state': 'OK', 'managed': True, 'reused': True, 'version': version}
                    raise RuntimeError('Servidor desta janela indisponível; pare e inicie novamente')
                self.close()
            version = _version(host)
            token.check()
            if version:
                return {'state': 'OK', 'managed': False, 'reused': True, 'version': version}
            executable = binary()
            if not executable:
                raise ValueError('Instale Ollama antes de iniciar o servidor')
            self._process = subprocess.Popen([executable, 'serve'], env=server_environment(host),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            self._host = host
            try:
                deadline = min(monotonic() + 15, token.deadline or float('inf'))
                while monotonic() < deadline:
                    token.check()
                    if self._process.poll() is not None:
                        raise RuntimeError('Ollama encerrou ao iniciar; confira instalação e porta local')
                    if owns_health_port(self._process.pid, host):
                        version = _version(host)
                        token.check()
                        if version:
                            return {'state': 'OK', 'managed': True, 'reused': False, 'version': version}
                    Event().wait(.05)
                raise TimeoutError('Servidor Ollama não ficou pronto em 15 segundos')
            except BaseException:
                self.close()
                raise

    def close(self):
        with self._lock:
            process = self._process
            if process is None:
                return False
            # Group includes runners, even if the parent has already exited.
            try:
                if os.name == 'posix':
                    try: os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                elif process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    if os.name != 'posix': process.kill()
            finally:
                if os.name == 'posix':
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                process.wait()
                self._process = None
                self._host = ''
            return True
