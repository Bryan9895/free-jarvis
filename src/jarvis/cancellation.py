"""Cancelamento cooperativo de novas ações; efeitos já enviados não são desfeitos."""
from threading import Event


class CancelledError(RuntimeError):
    pass


class CancellationToken:
    def __init__(self):
        self._event = Event()

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self):
        if self.cancelled:
            raise CancelledError("Tarefa cancelada; efeitos já enviados não foram desfeitos")
