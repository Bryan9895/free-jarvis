"""Interrompe leitura HTTP bloqueada sem ocupar a thread da interface."""
from threading import Event, Thread
from time import monotonic
import socket

from .cancellation import CancelledError


class ReadBudget:
    def __init__(self, response, *, token=None, deadline=None, first=30, idle=20):
        self.response, self.token, self.deadline = response, token, deadline
        self.first, self.idle = first, idle
        self.last = monotonic()
        self.received = False
        self.error = None
        self.done = Event()
        self.thread = Thread(target=self._watch, daemon=True, name='jarvis-http-budget')

    def __enter__(self):
        self.thread.start()
        return self

    def touch(self):
        self.last, self.received = monotonic(), True

    def check(self):
        if self.token is not None:
            self.token.check()
        if self.error is not None:
            raise self.error
        if self.deadline is not None and monotonic() >= self.deadline:
            raise TimeoutError('Prazo total da requisição excedido')

    def _watch(self):
        while not self.done.wait(.025):
            try:
                self.check()
                if monotonic() - self.last >= (self.idle if self.received else self.first):
                    raise TimeoutError('FCC sem eventos dentro do prazo configurado')
            except (CancelledError, TimeoutError) as exc:
                self.error = exc
                # close() pode aguardar o lock do BufferedReader; shutdown acorda
                # readline imediatamente. O context manager fecha o recurso depois.
                sock = getattr(getattr(getattr(self.response, 'fp', None), 'raw', None), '_sock', None)
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                return

    def __exit__(self, *_):
        self.done.set()
        self.thread.join(timeout=.1)
