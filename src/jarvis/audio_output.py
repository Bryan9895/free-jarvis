"""Síntese e reprodução ordenadas com no máximo dois WAVs aguardando."""
from contextvars import copy_context
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Event, Thread
import os
import tempfile

from .cancellation import CancelledError
from .latency import mark


class CombinedCancel:
    def __init__(self, *events):
        self.events = events

    def is_set(self):
        return any(event.is_set() for event in self.events)


def play_pipeline(voice, chunks):
    from .tts_engine import synthesizer
    ready, stopped = Queue(maxsize=2), Event()
    cancel = CombinedCancel(voice._speech_cancel, stopped)
    errors = []
    done = object()

    def send(value):
        while not cancel.is_set():
            try:
                ready.put(value, timeout=.05)
                return True
            except Full:
                pass
        return False

    def produce():
        try:
            for chunk in chunks:
                if cancel.is_set():
                    return
                fd, filename = tempfile.mkstemp(prefix='jarvis_speech_', suffix='.wav')
                os.close(fd)
                path = Path(filename)
                try:
                    mark('tts_synthesis_start')
                    synthesizer.synthesize(voice.piper_model, chunk, path, cancel)
                    mark('tts_synthesis_end')
                    if send(path):
                        path = None  # consumidor assume a limpeza
                finally:
                    if path is not None:
                        path.unlink(missing_ok=True)
        except BaseException as exc:
            errors.append(exc)
        finally:
            send(done)

    worker = Thread(target=copy_context().run, args=(produce,), daemon=True, name='jarvis-tts-producer')
    worker.start()
    try:
        while True:
            if voice._speech_cancel.is_set():
                raise CancelledError('Reprodução cancelada')
            try:
                item = ready.get(timeout=.05)
            except Empty:
                if not worker.is_alive():
                    break
                continue
            if item is done:
                break
            try:
                if voice._speech_cancel.is_set():
                    raise CancelledError('Reprodução cancelada')
                player = ['paplay', '--device=' + voice.output_device, str(item)] if voice.output_device else ['aplay', '-q', str(item)]
                mark('player_start_proxy')  # não comprova áudio físico no fone
                voice._run_audio(player)
                mark('player_end')
            finally:
                item.unlink(missing_ok=True)
        if errors:
            raise errors[0]
        return 'spoken'
    finally:
        stopped.set()
        worker.join(timeout=2)
        while not ready.empty():
            item = ready.get_nowait()
            if item is not done:
                item.unlink(missing_ok=True)


class LiveSpeech:
    """Ponte limitada entre deltas de texto e o pipeline de áudio."""
    def __init__(self, voice):
        from .speech_text import SentenceBuffer
        self.voice, self.buffer = voice, SentenceBuffer()
        self.queue = Queue(maxsize=2)
        self.closed, self.stopped = Event(), Event()
        self.text = ''
        self.error = None
        self.status = None
        self.worker = Thread(target=copy_context().run, args=(self._run,), daemon=True, name='jarvis-live-speech')
        self.worker.start()

    def _run(self):
        try:
            self.status = self.voice.speak_stream(self._chunks())
        except BaseException as exc:
            self.error = exc
        finally:
            self.stopped.set()

    def _chunks(self):
        while not self.voice._speech_cancel.is_set():
            try:
                yield self.queue.get(timeout=.05)
            except Empty:
                if self.closed.is_set():
                    return

    def _send(self, chunk):
        from .speech_text import spoken_text, speech_chunks
        for part in speech_chunks(spoken_text(chunk)):
            while not self.stopped.is_set() and not self.voice._speech_cancel.is_set():
                try:
                    self.queue.put(part, timeout=.05)
                    break
                except Full:
                    pass

    def feed(self, delta):
        self.text += delta
        for chunk in self.buffer.feed(delta):
            mark('first_sentence_available')
            self._send(chunk)

    def finish(self, final):
        if self.text and self.text != final:
            self.abort()
            raise RuntimeError('Resposta final divergiu do texto incremental; voz interrompida')
        if not self.text:
            self.buffer.feed(final)
            # Não perder frases extraídas ao receber resposta síncrona.
            self._send(final)
        else:
            for chunk in self.buffer.finish():
                self._send(chunk)
        self.closed.set()
        self.worker.join()
        if self.error is not None:
            raise self.error
        return self.status

    def abort(self):
        self.closed.set()
        self.voice.cancel_speech()
        self.worker.join(timeout=3)
