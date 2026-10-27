"""Ownership e eventos da captura compartilhados por conversa e diagnóstico."""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class CaptureEvent:
    session_id: str
    turn_id: str
    state: str
    reason: str
    at: float


class CaptureCoordinator:
    def __init__(self):
        self.lock = Lock()
        self.events = deque(maxlen=256)

    def transition(self, trace, state, reason, emit=lambda _: None):
        event = CaptureEvent(trace.session_id, trace.turn_id, state, reason, monotonic())
        self.events.append(event)
        emit(event)

    @contextmanager
    def output(self, cancelled):
        from .cancellation import CancelledError
        while not self.lock.acquire(timeout=.05):
            if cancelled.is_set():
                raise CancelledError('Saída cancelada antes da liberação da captura')
        try:
            yield
        finally:
            self.lock.release()


coordinator = CaptureCoordinator()
