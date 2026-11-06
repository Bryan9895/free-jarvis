"""Resident Kokoro subprocess with cancellable reads and bounded lifetime."""
import atexit
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import signal
import tempfile
import wave
from threading import Lock
from time import monotonic

from .cancellation import CancelledError


class KokoroSynthesizer:
    def __init__(self, *, own_session=True):
        self._lock = Lock()
        self._process = None
        self._key = None
        self.own_session = own_session

    def _close(self):
        if self._process is not None:
            process, self._process = self._process, None
            if os.name == 'posix' and self.own_session:
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                if os.name == 'posix' and self.own_session:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                else:
                    process.kill()
                process.wait()
            finally:
                # A child can outlive an already-exited worker and keep its pipes open.
                if os.name == 'posix' and self.own_session:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
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
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 300:
            raise ValueError('Prazo Kokoro deve estar entre 0 e 300 segundos')
        deadline = monotonic() + timeout
        def check():
            if cancel.is_set():
                raise CancelledError('Síntese Kokoro cancelada')
            if monotonic() >= deadline:
                raise TimeoutError('Tempo limite de síntese Kokoro excedido')
        check()
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 65536:
            raise ValueError('Trecho Kokoro vazio ou maior que 64 KiB; texto visual preservado')
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
        while not self._lock.acquire(timeout=min(.05, max(0, deadline - monotonic()))):
            check()
        stage = None
        try:
            check()
            try:
                target = Path(filename).absolute()
                descriptor, name = tempfile.mkstemp(prefix='.jarvis-kokoro-', suffix='.wav', dir=target.parent)
                os.close(descriptor)
                stage = Path(name)
                if self._key != key or self._process is None or self._process.poll() is not None:
                    self._close()
                    env = {k: v for k, v in os.environ.items() if k in ('HOME', 'PATH', 'LANG', 'LC_ALL', 'TMPDIR')}
                    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                               CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
                    self._process = subprocess.Popen([str(python), '-I', str(Path(__file__).with_name('kokoro_worker.py'))],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                        start_new_session=self.own_session)
                    self._key = key
                process = self._process
                request = (json.dumps({'directory': directory, 'text': text,
                                      'filename': str(stage)}, ensure_ascii=False) + '\n').encode()
                os.set_blocking(process.stdin.fileno(), False)
                remaining = memoryview(request)
                with selectors.DefaultSelector() as writer:
                    writer.register(process.stdin, selectors.EVENT_WRITE)
                    while remaining:
                        check()
                        if not writer.select(.05): continue
                        try:
                            sent = os.write(process.stdin.fileno(), remaining)
                        except BlockingIOError:
                            continue
                        if not sent: raise RuntimeError('Worker Kokoro não recebeu a solicitação')
                        remaining = remaining[sent:]
                buffer = b''
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        check()
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
                        check()
                        if not isinstance(event, dict):
                            raise ValueError('Resposta de síntese Kokoro inválida')
                        if event.get('error'):
                            raise RuntimeError('Worker Kokoro falhou; texto visual preservado')
                        if event.get('ok') is not True:
                            raise RuntimeError('Resultado de síntese Kokoro inválido')
                        validate_wav(stage, check)
                        check()
                        os.replace(stage, target)
                        return
            except BaseException:
                self._close()
                raise
        finally:
            if stage is not None:
                stage.unlink(missing_ok=True)
            self._lock.release()


def validate_wav(filename, check=lambda: None):
    try:
        if Path(filename).stat().st_size > 6 * 1024 * 1024:
            raise ValueError('WAV Kokoro excede o limite')
        with wave.open(str(filename), 'rb') as output:
            frames = output.getnframes()
            if (output.getframerate() != 24000 or output.getnchannels() != 1
                    or output.getsampwidth() != 2 or not 1 <= frames <= 24000 * 120):
                raise ValueError('Worker Kokoro não produziu WAV PCM16 mono de 24 kHz válido')
            read = 0
            while data := output.readframes(65536):
                check()
                read += len(data)
            if read != frames * 2:
                raise ValueError('WAV Kokoro truncado; áudio descartado')
    except (wave.Error, EOFError) as exc:
        raise ValueError('WAV Kokoro inválido; áudio descartado') from exc


kokoro_synthesizer = KokoroSynthesizer()
atexit.register(kokoro_synthesizer.close)
