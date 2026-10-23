"""Normalização única e VAD local; nível RMS continua sendo só diagnóstico."""
import numpy as np


class PCMNormalizer:
    def __init__(self, source_rate, target_rate=16000):
        self.source_rate = source_rate
        self.target_rate = target_rate
        self._resampler = None
        if source_rate != target_rate:
            import av
            self._resampler = av.AudioResampler(format='s16', layout='mono', rate=target_rate)

    def feed(self, pcm):
        if pcm.ndim == 2:
            pcm = np.mean(pcm, axis=1).astype(np.int16)
        if self._resampler is None:
            return pcm
        import av
        frame = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format='s16', layout='mono')
        frame.sample_rate = self.source_rate
        frames = self._resampler.resample(frame)
        return np.concatenate([item.to_ndarray().reshape(-1) for item in frames]) if frames else np.empty(0, dtype=np.int16)

    def flush(self):
        if self._resampler is None:
            return np.empty(0, dtype=np.int16)
        frames = self._resampler.resample(None)
        return np.concatenate([item.to_ndarray().reshape(-1) for item in frames]) if frames else np.empty(0, dtype=np.int16)


class SileroActivity:
    """Janela limitada com contexto; usa apenas API pública do faster-whisper.

    O classificador é reinvocado com 512 ms de contexto, sem depender do layout
    privado de estados ONNX. Limiar ainda exige calibração acústica no notebook.
    """
    def __init__(self, threshold=0.5):
        from faster_whisper.vad import get_vad_model
        self.model = get_vad_model()
        self.threshold = threshold
        self._recent = np.empty(0, dtype=np.float32)

    def active(self, pcm):
        samples = pcm.astype(np.float32) / 32768
        self._recent = np.concatenate((self._recent, samples))[-8192:]
        if not len(samples):
            return False
        padding = (-len(self._recent)) % 512
        window = np.pad(self._recent, (0, padding))
        probabilities = np.asarray(self.model(window)).reshape(-1)
        count = max(1, int(np.ceil(len(samples) / 512)))
        return bool(np.max(probabilities[-count:]) >= self.threshold)
