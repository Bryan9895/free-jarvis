"""Controlador compartilhado de turnos sobre o executor existente."""
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from uuid import uuid4

from .cancellation import CancelledError
from .speech_text import ResponseText


@dataclass(frozen=True)
class ConversationEvent:
    session_id: str
    turn_id: str
    state: str
    reason: str
    at: float


class ConversationController:
    def __init__(self, service, *, emit=lambda _: None):
        self.service = service
        self.emit = emit
        self.session_id = uuid4().hex
        self._turn_id = None
        self._cancelled = False
        self._lock = Lock()
        self._guard = Lock()
        self._voice = None

    def _event(self, turn, state, reason):
        self.emit(ConversationEvent(self.session_id, turn, state, reason, monotonic()))

    def _check(self, turn):
        with self._guard:
            if self._turn_id != turn or self._cancelled:
                raise CancelledError("Turno cancelado; resultado atrasado descartado")

    def cancel(self):
        with self._guard:
            self._cancelled = True
            turn, voice = self._turn_id, self._voice
        self.service.cancel_current()
        if voice is not None:
            voice.cancel_speech()
        if turn:
            self._event(turn, 'cancelado', 'solicitado pelo usuário')

    def run(self, message, *, voice=None, display=lambda _: None):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Já há um turno em execução")
        turn = uuid4().hex
        with self._guard:
            self._turn_id, self._cancelled, self._voice = turn, False, voice
        try:
            if voice is not None:
                voice.prepare_speech()
            self._check(turn)
            self._event(turn, 'executando', 'intenção recebida')
            response = ResponseText.from_display(self.service.ask(message))
            self._check(turn)
            display(response.display_text)
            if voice is not None:
                self._check(turn)
                self._event(turn, 'falando', 'resposta disponível')
                try:
                    status = voice.speak(response.spoken_text)
                    self._check(turn)
                    if status == 'disabled':
                        self._event(turn, 'erro', 'tts: voz local não configurada')
                        return response
                except CancelledError:
                    raise
                except Exception as exc:
                    self._check(turn)
                    self._event(turn, 'erro', 'tts: ' + str(exc))
                    return response
            self._check(turn)
            self._event(turn, 'aguardando_seguimento', 'turno finalizado')
            return response
        except CancelledError:
            raise
        except Exception:
            self._event(turn, 'erro', 'modelo/execução: resposta indisponível')
            raise
        finally:
            with self._guard:
                self._voice = None
            self._lock.release()
