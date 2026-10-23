"""Conversa por ativação local sem Enter nem revisão obrigatória."""
from __future__ import annotations

import queue

from .voice import VoiceIO, WakeWordConversation


def run_voice_session(service, voice: VoiceIO, *, report=print, listener_factory=WakeWordConversation):
    commands = queue.Queue(maxsize=1)

    def status(message):
        report(message)
        if message.startswith("Escuta contínua indisponível:"):
            try:
                commands.put_nowait(None)
            except queue.Full:
                pass

    listener = listener_factory(voice, commands.put, status)
    listener.start()
    report("Voz contínua ativa. Diga 'Jarvis' seguido do pedido. "
           "Diga 'Jarvis, sair' ou pressione Ctrl+C para encerrar.")
    try:
        while True:
            try:
                command = commands.get(timeout=0.2)
            except queue.Empty:
                continue
            if command is None:
                break
            try:
                if command.casefold().strip(" .,!?:;") in {"sair", "encerrar jarvis"}:
                    break
                report("Você (voz) > " + command)
                answer = service.ask(command)
                report("JARVIS > " + answer)
                if voice.speak(answer) == "disabled":
                    report("Resposta em texto; configure JARVIS_PIPER_MODEL para ouvir.")
            except Exception as exc:
                report("Falha no turno de voz: " + str(exc))
            finally:
                listener.resume()
    except KeyboardInterrupt:
        service.cancel_current()
        report("Conversa por voz encerrada.")
    finally:
        listener.stop()


class MixedInput:
    """Texto e voz no mesmo loop; stdin só é lido pela thread principal."""

    def __init__(self, voice, *, report=print, listener_factory=WakeWordConversation):
        self.report = report
        self.commands = queue.Queue()
        self.listener = listener_factory(voice, self.commands.put, report)

    def start(self):
        self.listener.start()
        self.report("Digite sua mensagem ou diga 'Jarvis' seguido do pedido. Ctrl+C encerra.")

    def read(self, stdin, *, ready=None):
        import select
        if ready is None:
            ready = lambda: bool(select.select([stdin], [], [], 0.1)[0])
        self.listener.resume()
        self.report("Você > ")
        while True:
            try:
                message = self.commands.get_nowait()
            except queue.Empty:
                message = None
            if message is not None:
                self.listener.pause()
                self.report("Você (voz) > " + message)
                return message
            if ready():
                line = stdin.readline()
                if not line:
                    raise EOFError
                self.listener.pause()
                return line.strip()

    def close(self):
        self.listener.stop()
