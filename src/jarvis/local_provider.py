"""Responses bridge to the pinned OpenJarvis engine in an isolated interpreter.

No FCC client, discovery, download or cloud fallback is used by this provider.
The child only performs inference; tool calls are returned to Agent/Toolkit.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
from time import monotonic
from urllib.parse import urlsplit

from .cancellation import CancellationToken
from .fcc import FCCError

OPENJARVIS_REVISION = '324c9c3ac61bff07a0d99b715a7511dcd78600c4'


def local_host(value):
    parsed = urlsplit(value)
    try:
        valid = ipaddress.ip_address(parsed.hostname or '').is_loopback
        port = parsed.port
    except ValueError:
        valid, port = False, None
    if (not valid or parsed.scheme != 'http' or not port or parsed.username
            or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('O perfil Local exige URL HTTP com IP de loopback e porta, sem credenciais')
    return value.rstrip('/')


def local_model(name):
    if (not isinstance(name, str) or not name or len(name) > 256
            or any(c.isspace() for c in name) or '/' in name or ':cloud' in name.lower()):
        raise FCCError('Use um modelo instalado localmente, sem provedor, URL ou tag :cloud')
    return name


class OpenJarvisProvider:
    def __init__(self, *, model='gemma4:e2b', host='http://127.0.0.1:11434', python=''):
        self.preferred = local_model(model)
        self.active_model = self.preferred
        self.host = local_host(host)
        self.python = python or sys.executable
        self.known_models = ()

    def _exchange(self, request, *, on_event=None, cancel_token=None, deadline=None):
        token = cancel_token or CancellationToken()
        limit = min(deadline or monotonic() + 120, token.deadline or float('inf'))
        token.check()
        from .latency import mark
        mark('local_worker_start')
        # Clear cloud/proxy credentials in the isolated engine's environment.
        env = {k: v for k, v in os.environ.items() if k in
               ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT')}
        worker = Path(__file__).with_name('openjarvis_worker.py')
        request = {**request, 'host': self.host, 'revision': OPENJARVIS_REVISION}
        try:
            child = subprocess.Popen([self.python, '-I', str(worker)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        except OSError as exc:
            raise FCCError('Python do OpenJarvis indisponível; configure JARVIS_OPENJARVIS_PYTHON') from exc
        try:
            child.stdin.write((json.dumps(request, ensure_ascii=False) + '\n').encode())
            child.stdin.close()
            buffer = b''
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    token.check()
                    if monotonic() >= limit:
                        raise TimeoutError('Prazo do motor local excedido')
                    if not selector.select(min(.05, max(0, limit - monotonic()))):
                        continue
                    data = os.read(child.stdout.fileno(), 65536)
                    if not data:
                        raise FCCError('Motor OpenJarvis encerrou sem resultado; confira a instalação isolada')
                    buffer += data
                    if len(buffer) > 4 * 1024 * 1024:
                        raise FCCError('Resultado local excedeu o limite de transporte')
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        event = json.loads(line)
                        token.check()
                        if monotonic() >= limit:
                            raise TimeoutError('Prazo do motor local excedido')
                        if event.get('error'):
                            raise FCCError(event['error'])
                        if event.get('ready'):
                            mark('local_worker_ready')
                        if 'delta' in event and on_event is not None:
                            on_event({'type': 'response.output_text.delta', 'delta': event['delta']})
                        if 'result' in event:
                            return event['result']
        except TimeoutError:
            raise
        except (OSError, ValueError) as exc:
            raise FCCError('Falha no protocolo do motor local') from exc
        finally:
            if not child.stdin.closed:
                child.stdin.close()
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            child.stdout.close()

    def available_models(self):
        models = self._exchange({'operation': 'models'})
        self.known_models = tuple(m for m in models if _allowed_model(m))
        return list(self.known_models)

    def initialize(self):
        return self.select_model(self.preferred)

    def select_model(self, name):
        local_model(name)
        if name not in self.available_models():
            raise FCCError('Modelo local ausente. Provisione explicitamente o Ollama e seus pesos')
        self._exchange({'operation': 'check', 'model': name})
        self.active_model = name
        return name

    def fork(self, model=''):
        copied = type(self)(model=model or self.active_model, host=self.host, python=self.python)
        copied.known_models = self.known_models
        if model and model not in self.known_models:
            raise FCCError('Modelo de especialista não está instalado localmente')
        return copied

    def use_all_models(self):
        raise FCCError('O perfil Local não permite fallback automático; selecione um modelo explicitamente')

    def responses(self, payload):
        return self.stream_responses(payload)

    def stream_responses(self, payload, *, on_event=None, cancel_token=None, deadline=None):
        # The selected session model wins over stale IDs in Agent/planner payloads.
        return self._exchange({'operation': 'generate', 'model': self.active_model,
                               'payload': payload}, on_event=on_event,
                              cancel_token=cancel_token, deadline=deadline)

    def close(self):
        pass  # Every exchange reaps its isolated process, including cancellation.


def _allowed_model(name):
    try:
        local_model(name)
        return True
    except FCCError:
        return False
