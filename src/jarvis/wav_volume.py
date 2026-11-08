"""Redução de volume independente do nível do sistema PipeWire/ALSA.

Somente PCM16 WAV. Não altera o áudio do microfone nem aumenta volume;
o arquivo é substituído atomicamente após processar todos os quadros.
"""
from array import array
import os
from pathlib import Path
import sys
import tempfile
import wave

from .cancellation import CancelledError


def attenuate_wav(path, gain, cancel=None):
    path = Path(path)
    if type(gain) not in (float, int) or not 0 <= gain <= 1:
        raise ValueError("Volume ADAM deve estar entre 0% e 100%")
    if gain == 1:
        return
    fd, tmpname = tempfile.mkstemp(prefix='.adam-volume-', suffix='.wav', dir=path.parent)
    os.close(fd)
    tmp = Path(tmpname)
    try:
        with wave.open(str(path), 'rb') as source, wave.open(str(tmp), 'wb') as target:
            if source.getcomptype() != 'NONE' or source.getsampwidth() != 2:
                raise ValueError('Volume requer WAV PCM16 sem compressão')
            target.setparams(source.getparams())
            while True:
                if cancel is not None and cancel.is_set():
                    raise CancelledError('Volume de voz cancelado')
                data = source.readframes(4096)
                if not data:
                    break
                samples = array('h')
                samples.frombytes(data)
                if sys.byteorder != 'little':
                    samples.byteswap()
                samples = array('h', (max(-32768, min(32767, round(v * gain))) for v in samples))
                if sys.byteorder != 'little':
                    samples.byteswap()
                target.writeframesraw(samples.tobytes())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
