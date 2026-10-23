"""Piper CPU residente em processo cancelável; uma voz por processo principal."""
import atexit
import multiprocessing
from pathlib import Path
from threading import Lock
from time import monotonic
import wave

from .cancellation import CancelledError


def _worker(connection, model):
    try:
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from piper import PiperVoice
        voice = PiperVoice.load(model, use_cuda=False)
        while True:
            request = connection.recv()
            if request is None:
                return
            text, filename = request
            try:
                with wave.open(filename, 'wb') as output:
                    voice.synthesize_wav(text, output)
                connection.send(None)
            except Exception as exc:
                connection.send(type(exc).__name__ + ': ' + str(exc))
    except EOFError:
        pass
    except Exception as exc:
        try:
            connection.send(type(exc).__name__ + ': ' + str(exc))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


class PiperSynthesizer:
    def __init__(self):
        self._lock = Lock()
        self._process = None
        self._connection = None
        self._model = None

    def _close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if self._process is not None:
            if self._process.pid is not None:
                if self._process.is_alive():
                    self._process.terminate()
                self._process.join(timeout=0.5)
                if self._process.is_alive():
                    self._process.kill()
                    self._process.join(timeout=0.5)
            self._process.close()
            self._process = None
        self._model = None

    def close(self):
        with self._lock:
            self._close()

    def synthesize(self, model, text, filename, cancel, *, timeout=90):
        model = str(Path(model).resolve())
        with self._lock:
            try:
                if cancel.is_set():
                    raise CancelledError('Síntese cancelada')
                if self._model != model or self._process is None or not self._process.is_alive():
                    self._close()
                    context = multiprocessing.get_context('spawn')
                    parent, child = context.Pipe()
                    process = context.Process(target=_worker, args=(child, model), daemon=True,
                                              name='jarvis-piper-cpu')
                    self._process, self._connection, self._model = process, parent, model
                    try:
                        process.start()
                    finally:
                        child.close()
                self._connection.send((text, str(filename)))
                deadline = monotonic() + timeout
                while True:
                    if cancel.is_set():
                        raise CancelledError('Síntese cancelada')
                    if monotonic() >= deadline:
                        raise RuntimeError('Tempo limite de síntese Piper excedido')
                    if self._connection.poll(0.05):
                        error = self._connection.recv()
                        if error:
                            raise RuntimeError('Piper: ' + error)
                        return
                    if not self._process.is_alive():
                        raise RuntimeError('Processo Piper encerrou sem áudio')
            except BaseException:
                self._close()
                raise


synthesizer = PiperSynthesizer()
atexit.register(synthesizer.close)
