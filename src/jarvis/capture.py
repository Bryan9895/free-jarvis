"""Ownership e eventos da captura compartilhados por conversa e diagnóstico."""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from time import monotonic
import os
from pathlib import Path
from threading import Event
from queue import Queue, Full, Empty


class FrameLossError(RuntimeError):
    pass


class FrameSubscription:
    def __init__(self, capacity):
        self.queue = Queue(maxsize=capacity)
        self.lost = 0

    def receive(self):
        if self.lost:
            raise FrameLossError('Consumidor de áudio perdeu quadros; turno deve ser descartado')
        return self.queue.get_nowait()


class FrameBus:
    """Bounded distribution of already-normalized PCM; subscribers own no device."""
    def __init__(self):
        self._guard = Lock()
        self._subscriptions = []

    @contextmanager
    def subscribe(self, capacity=8):
        if not 1 <= capacity <= 64:
            raise ValueError('Fila de áudio deve ter entre 1 e 64 quadros')
        subscription = FrameSubscription(capacity)
        with self._guard:
            if len(self._subscriptions) >= 8:
                raise RuntimeError('Limite de consumidores de áudio atingido')
            self._subscriptions.append(subscription)
        try:
            yield subscription
        finally:
            with self._guard:
                self._subscriptions.remove(subscription)
            while True:
                try: subscription.queue.get_nowait()
                except Empty: break

    def publish(self, pcm):
        frame = pcm.copy()
        frame.flags.writeable = False
        with self._guard:
            for subscription in self._subscriptions:
                try:
                    subscription.queue.put_nowait(frame)
                except Full:
                    subscription.lost += 1


class CaptureLock:
    """One capture/output owner across GUI, CLI and active Doctor processes."""
    def __init__(self, path=None):
        self._lock = Lock()
        self._stream = None
        self.path = path

    def acquire(self, blocking=True, timeout=-1):
        if not self._lock.acquire(blocking, timeout):
            return False
        if os.name != 'posix':
            return True
        import fcntl
        deadline = monotonic() + timeout if timeout >= 0 else float('inf')
        try:
            path = Path(self.path) if self.path else Path.home() / '.cache/jarvis-fcc/capture.lock'
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            self._stream = os.fdopen(descriptor, 'a')
            while True:
                try:
                    fcntl.flock(self._stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True
                except BlockingIOError:
                    if not blocking or monotonic() >= deadline:
                        self._stream.close()
                        self._stream = None
                        self._lock.release()
                        return False
                    Event().wait(min(.02, max(0, deadline - monotonic())))
        except BaseException:
            if self._stream:
                self._stream.close()
                self._stream = None
            self._lock.release()
            raise

    def locked(self):
        return self._lock.locked()

    def release(self):
        if self._stream:
            self._stream.close()
            self._stream = None
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()


@dataclass(frozen=True)
class CaptureEvent:
    session_id: str
    turn_id: str
    state: str
    reason: str
    at: float


class CaptureCoordinator:
    def __init__(self):
        self.lock = CaptureLock()
        self.events = deque(maxlen=256)
        self.frames = FrameBus()

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
