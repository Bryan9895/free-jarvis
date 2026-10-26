"""Traços limitados em memória; conteúdo de conversas não entra nas métricas."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from uuid import uuid4
import math

_current = ContextVar('jarvis_latency', default=None)


class TracedText(str):
    def __new__(cls, value, trace=None):
        result = super().__new__(cls, value)
        result.trace = trace or TurnTrace()
        return result


@dataclass
class TurnTrace:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    turn_id: str = field(default_factory=lambda: uuid4().hex)
    events: list = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def mark(self, stage, *, at=None, request_id=None, attempt=None, round=None):
        # Esquema fechado: não aceitar texto, argumentos, caminhos ou tokens.
        item = {'stage': stage, 'at': monotonic() if at is None else at}
        for key, value in (('request_id', request_id), ('attempt', attempt), ('round', round)):
            if value is not None:
                item[key] = value
        with self._lock:
            if len(self.events) < 2048:
                self.events.append(item)

    def snapshot(self):
        with self._lock:
            return {'session_id': self.session_id, 'turn_id': self.turn_id,
                    'events': [dict(item) for item in self.events]}


def mark(stage, **attributes):
    trace = _current.get()
    if trace is not None:
        trace.mark(stage, **attributes)


def current_trace():
    return _current.get()


@contextmanager
def tracing(trace):
    token = _current.set(trace)
    try:
        yield trace
    finally:
        _current.reset(token)


def summary(values):
    """Percentil nearest-rank; nunca soma percentis de etapas distintas."""
    ordered = sorted(values)
    if not ordered:
        return {'n': 0, 'p50': None, 'p95': None, 'worst': None}
    return {'n': len(ordered), 'p50': ordered[math.ceil(len(ordered) * .5) - 1],
            'p95': ordered[math.ceil(len(ordered) * .95) - 1], 'worst': ordered[-1]}
