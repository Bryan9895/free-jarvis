"""Optional single-clap candidate detector. Physical acceptance remains separate."""
from time import monotonic


class ClapDetector:
    def __init__(self, debounce=1.5):
        self.debounce = debounce
        self.last = float('-inf')

    def process(self, pcm, *, enabled=True, now=None):
        if not enabled:
            return False
        import numpy as np
        samples = np.asarray(pcm, dtype=np.float32).reshape(-1) / 32768
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
        now = monotonic() if now is None else now
        if now - self.last < self.debounce:
            return False
        self.last = now
        return True
