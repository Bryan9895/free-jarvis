"""Cancelamento cooperativo de novas ações; efeitos já enviados não são desfeitos."""
from threading import Event
from time import monotonic


class CancelledError(RuntimeError):
    pass


class CancellationToken:
    def __init__(self, *, deadline=None):
        self._event = Event()
        self.deadline = deadline

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self):
        if self.cancelled:
            raise CancelledError("Tarefa cancelada; efeitos já enviados não foram desfeitos")
        if self.deadline is not None and monotonic() >= self.deadline:
            raise TimeoutError('Prazo total do turno excedido; confira os efeitos antes de repetir')
