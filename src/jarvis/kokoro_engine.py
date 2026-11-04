"""Resident Kokoro subprocess with cancellable reads and bounded lifetime."""
import atexit
import json
import os
from pathlib import Path
import selectors
import subprocess
import wave
from threading import Lock
from time import monotonic

from .cancellation import CancelledError


class KokoroSynthesizer:
    def __init__(self):
        self._lock = Lock()
        self._process = None
        self._key = None

    def _close(self):
        if self._process is not None:
            process, self._process = self._process, None
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass
        self._key = None

    def close(self):
        with self._lock:
            self._close()

    def synthesize(self, directory, text, filename, cancel, *, python='', timeout=90):
        if cancel.is_set():
            raise CancelledError('Síntese Kokoro cancelada')
        from .kokoro_setup import runtime_python
        directory = str(Path(directory).expanduser().resolve())
        python = python or runtime_python()
        if not python:
            raise RuntimeError('Instale o runtime: jarvis-fcc kokoro install-runtime')
        from .kokoro_assets import FILES
        try:
            fingerprint = tuple((name, (Path(directory) / name).stat().st_mtime_ns,
                                  (Path(directory) / name).stat().st_size) for name in (*FILES, 'SOURCE.json'))
        except OSError as exc:
            raise RuntimeError('Instale os pesos: jarvis-fcc kokoro install-voice') from exc
        key = (directory, str(python), fingerprint)
        with self._lock:
            try:
                if cancel.is_set():
                    raise CancelledError('Síntese Kokoro cancelada')
                if self._key != key or self._process is None or self._process.poll() is not None:
                    self._close()
                    env = {k: v for k, v in os.environ.items() if k in ('HOME', 'PATH', 'LANG', 'LC_ALL', 'TMPDIR')}
                    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                               CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
                    self._process = subprocess.Popen([str(python), '-I', str(Path(__file__).with_name('kokoro_worker.py'))],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
                    self._key = key
                process = self._process
                process.stdin.write((json.dumps({'directory': directory, 'text': text,
                                                'filename': str(filename)}, ensure_ascii=False) + '\n').encode())
                process.stdin.flush()
                deadline = monotonic() + timeout
                buffer = b''
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        if cancel.is_set():
                            raise CancelledError('Síntese Kokoro cancelada')
                        if monotonic() >= deadline:
                            raise TimeoutError('Tempo limite de síntese Kokoro excedido')
                        if not selector.select(.05):
                            continue
                        data = os.read(process.stdout.fileno(), 65536)
                        if not data:
                            raise RuntimeError('Worker Kokoro encerrou sem áudio')
                        buffer += data
                        if len(buffer) > 65536:
                            raise RuntimeError('Resposta inválida do worker Kokoro')
                        if b'\n' not in buffer:
                            continue
                        event = json.loads(buffer.split(b'\n', 1)[0])
                        if cancel.is_set():
                            raise CancelledError('Síntese Kokoro cancelada')
                        if event.get('error'):
                            raise RuntimeError('Kokoro: ' + event['error'])
                        if event.get('ok') is not True:
                            raise RuntimeError('Resultado de síntese Kokoro inválido')
                        with wave.open(str(filename), 'rb') as output:
                            if (output.getframerate() != 24000 or output.getnchannels() != 1
                                    or output.getsampwidth() != 2 or output.getnframes() < 1):
                                raise ValueError('Worker Kokoro não produziu WAV PCM16 mono de 24 kHz')
                        return
            except BaseException:
                self._close()
                raise


kokoro_synthesizer = KokoroSynthesizer()
atexit.register(kokoro_synthesizer.close)
