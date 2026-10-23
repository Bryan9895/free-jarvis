"""Negociação local; nunca altera a entrada padrão Pulse/PipeWire."""
from dataclasses import dataclass


@dataclass(frozen=True)
class InputFormat:
    rate: int
    channels: int
    name: str


def input_format(backend, device, preferred_rate=16000):
    # Backends de frames dos testes podem oferecer apenas InputStream.
    if not hasattr(backend, 'check_input_settings'):
        return InputFormat(preferred_rate, 1, str(device or 'padrão'))
    info = backend.query_devices(device, kind='input')
    native = int(info['default_samplerate'])
    channels = min(2, int(info['max_input_channels']))
    for rate, count in dict.fromkeys(((preferred_rate, 1), (native, 1), (native, channels))):
        if count < 1 or rate <= 0:
            continue
        try:
            backend.check_input_settings(device=device, channels=count, samplerate=rate, dtype='int16')
            return InputFormat(rate, count, str(info['name']))
        except Exception:
            continue
    raise RuntimeError('Entrada não aceita PCM16 mono/estéreo nas taxas consultadas; selecione outra entrada')
