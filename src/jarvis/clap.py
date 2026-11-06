"""Optional single-clap candidate detector. Physical acceptance remains separate."""
from time import monotonic
from dataclasses import dataclass


class ClapDetector:
    def __init__(self, debounce=1.5):
        self.debounce = debounce
        self.last = float('-inf')
        self.reset()

    def reset(self):
        self._window = None
        self.tail = None

    def process(self, pcm, *, enabled=True, now=None):
        if not enabled:
            self.reset()
            return False
        now = monotonic() if now is None else now
        if now - self.last < self.debounce:
            self.reset()
            return False
        import numpy as np
        incoming = np.asarray(pcm, dtype=np.int16).reshape(-1)
        if not len(incoming):
            return False
        self._window = (np.concatenate((self._window, incoming)) if self._window is not None else incoming)[-2560:].copy()
        samples = self._window.astype(np.float32) / 32768
        if len(samples) < 640:
            return False
        magnitude = np.abs(samples)
        peak = float(magnitude.max())
        rms = float(np.sqrt(np.mean(samples * samples)))
        if peak < .4 or rms < .02 or peak < 4 * rms:
            return False
        hot = np.flatnonzero(magnitude >= max(.2, peak * .3))
        if not len(hot) or hot[-1] - hot[0] > 240:
            return False
        # Require quiet around the impulse; a sustained tone/speech is not a clap.
        if hot[0] < 160 or hot[-1] >= len(samples) - 320:
            return False
        quiet = np.concatenate((samples[:hot[0]], samples[hot[-1] + 1:]))
        if float(np.sqrt(np.mean(quiet * quiet))) > .02:
            return False
        self.last = now
        self.tail = self._window[hot[-1] + 1:].copy()
        self._window = None
        return True


@dataclass(frozen=True)
class ActivationFrame:
    pcm: object
    at: float | None
    activated: bool = False


class ClapGate:
    """Hold one frame before fallback VAD, preserving every non-clap sample."""
    def __init__(self, detector):
        self.detector = detector
        self.detector.reset()
        self.pending = None

    def feed(self, pcm, *, enabled, defer=False, at=None, now=None):
        if self.detector.process(pcm, enabled=enabled, now=now):
            self.pending = None
            return ActivationFrame(self.detector.tail, at, True)
        current = ActivationFrame(pcm, at)
        if enabled and defer:
            ready, self.pending = self.pending, current
            return ready or ActivationFrame(None, None)
        if self.pending is not None:
            import numpy as np
            current = ActivationFrame(np.concatenate((self.pending.pcm, pcm)), at)
            self.pending = None
        return current

    def flush(self):
        ready, self.pending = self.pending, None
        return ready or ActivationFrame(None, None)
