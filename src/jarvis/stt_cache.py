"""Um único Whisper residente por processo, carregado sob demanda na CPU."""
from contextlib import contextmanager
from threading import Lock
import gc

_lock = Lock()
_model = None
_name = None


@contextmanager
def whisper_model(name):
    global _model, _name
    with _lock:
        if _model is None or _name != name:
            _model, _name = None, None
            gc.collect()
            from faster_whisper import WhisperModel
            model = WhisperModel(name, device='cpu', compute_type='int8')
            _model, _name = model, name
        yield _model
