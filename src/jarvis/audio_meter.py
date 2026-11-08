"""Envelope RMS do WAV que está sendo reproduzido; sem segunda captura de microfone."""
from array import array
from math import sqrt
from pathlib import Path
from threading import Event
import wave


def follow_wav(filename, emit, stop: Event, *, interval=0.06):
    """Medidor aproximado do áudio de saída (não mede som efetivo do alto-falante)."""
    try:
        with wave.open(str(Path(filename)), "rb") as sound:
            if sound.getsampwidth() != 2:
                return
            rate = sound.getframerate()
            block = max(1, round(rate * interval))
            while not stop.is_set():
                raw = sound.readframes(block)
                if not raw:
                    return
                values = array("h")
                values.frombytes(raw)
                if not values:
                    return
                level = sqrt(sum(x * x for x in values) / len(values)) / 32768.0
                emit(min(1., level * 6))
                if stop.wait(len(values) / max(1, rate)):
                    return
    except (OSError, ValueError, EOFError, wave.Error):
        return
    finally:
        try:
            emit(0.0)
        except Exception:
            pass
