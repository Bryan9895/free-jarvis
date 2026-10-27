"""Controlador compartilhado de turnos sobre o executor existente."""
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from uuid import uuid4

from .cancellation import CancelledError
from .speech_text import ResponseText
from .latency import TurnTrace, tracing, mark


class TextMailbox:
    """Um evento pendente por turno, independentemente do número de tokens."""
    def __init__(self, notify):
        self.text = ''
        self.pending = False
        self.lock = Lock()
        self.notify = notify

    def publish(self, delta):
        with self.lock:
            self.text += delta
            send = not self.pending
            self.pending = True
        if send:
            self.notify(self)

    def take(self):
        with self.lock:
            self.pending = False
            return self.text


class TerminalText:
    def __init__(self):
        self.text = ''

    def delta(self, text):
        if not self.text:
            print('JARVIS > ', end='', flush=True)
        self.text += text
        print(text, end='', flush=True)

    def finish(self, text):
        if self.text == text:
            print('\n')
        else:
            print(('\n' if self.text else '') + 'JARVIS > ' + text + '\n')


@dataclass(frozen=True)
class ConversationEvent:
    session_id: str
    turn_id: str
    state: str
    reason: str
    at: float


class ConversationController:
    def __init__(self, service, *, emit=lambda _: None, on_end=lambda: None, session_id=None):
        self.service = service
        self.emit = emit
        self.on_end = on_end
        self.session_id = session_id or uuid4().hex
        self._turn_id = None
        self._cancelled = False
        self._lock = Lock()
        self._guard = Lock()
        self._voice = None
        self.last_trace = None

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
        if turn and self.last_trace is not None:
            self.last_trace.mark('cancel_requested')
        self.service.cancel_current()
        if voice is not None:
            voice.cancel_speech()
        if turn:
            self._event(turn, 'cancelado', 'solicitado pelo usuário')

    def run(self, message, *, voice=None, display=lambda _: None, on_text=None, trace=None):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Já há um turno em execução")
        trace = trace or getattr(message, 'trace', None) or TurnTrace(session_id=self.session_id)
        if trace.session_id != self.session_id and getattr(message, 'trace', None) is not None:
            self.session_id = trace.session_id
        turn = trace.turn_id
        self.last_trace = trace
        trace.mark('intent_accepted')
        live = None
        with self._guard:
            self._turn_id, self._cancelled, self._voice = turn, False, voice
        try:
            if message.casefold().strip(' .,!?:;') == 'parar conversa':
                self.on_end()
                self._event(turn, 'cancelado', 'conversa encerrada pelo usuário')
                response = ResponseText.from_display('Conversa encerrada.')
                display(response.display_text)
                return response
            if voice is not None:
                voice.prepare_speech()
                if on_text is not None and callable(getattr(type(voice), 'speak_stream', None)):
                    from .audio_output import LiveSpeech
                    with tracing(trace):
                        live = LiveSpeech(voice)
            self._check(turn)
            self._event(turn, 'executando', 'intenção recebida')
            def receive(delta):
                self._check(turn)
                if on_text is not None:
                    on_text(delta)
                    mark('visual_delta')
                if live is not None:
                    live.feed(delta)
            with tracing(trace):
                if on_text is not None and callable(getattr(type(self.service), 'ask_stream', None)):
                    answer = self.service.ask_stream(message, on_text=receive)
                else:
                    answer = self.service.ask(message)
            response = ResponseText.from_display(answer)
            self._check(turn)
            display(response.display_text)
            trace.mark('visual_final')
            if voice is not None:
                self._check(turn)
                self._event(turn, 'falando', 'resposta disponível')
                try:
                    with tracing(trace):
                        status = live.finish(response.display_text) if live is not None else voice.speak(response.spoken_text)
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
            if live is not None and live.worker.is_alive():
                live.abort()
            trace.mark('turn_released')
            metrics = getattr(getattr(self.service, 'agent', None), 'last_metrics', None)
            if isinstance(metrics, dict):
                metrics['latency'] = trace.snapshot()
            with self._guard:
                self._voice = None
                self._turn_id = None
            self._lock.release()
