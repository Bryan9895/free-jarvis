"""Adaptador acústico opcional: sem artefato aceito, permanece o fallback STT.

Contrato de artefato próprio: ONNX recebe PCM float32 mono 16 kHz [1, 16000]
e retorna uma probabilidade escalar. Não aceita hey_jarvis como Jarvis isolado.
"""
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Protocol


class WakeWordEngine(Protocol):
    available: bool

    def process(self, pcm) -> bool: ...
    def reset(self): ...


@dataclass(frozen=True)
class WakeArtifact:
    model: Path
    sha256: str
    license: str
    threshold: float

    @classmethod
    def load(cls, filename):
        path = Path(filename).expanduser()
        data = json.loads(path.read_text())
        if (data.get('version') != 1 or data.get('keyword', '').casefold() != 'jarvis'
                or data.get('language') != 'pt-BR' or data.get('format') != 'pcm_float32_16000'
                or not isinstance(data.get('license'), str) or not data['license'].strip()):
            raise ValueError('Manifesto deve identificar Jarvis isolado pt-BR, formato e licença')
        evaluation = data.get('evaluation', {})
        if not isinstance(evaluation, dict):
            raise ValueError('Avaliação acústica inválida')
        calls, correct, negatives, false = (evaluation.get(key) for key in
            ('calls', 'correct', 'negative_minutes', 'false_activations'))
        if (type(calls) is not int or type(correct) is not int or calls < 20
                or not 0 <= correct <= calls or correct / calls < .9
                or type(negatives) not in (int, float) or not math.isfinite(negatives) or negatives < 30
                or type(false) is not int or not 0 <= false <= 1
                or not isinstance(evaluation.get('evidence'), str) or not evaluation['evidence'].strip()):
            raise ValueError('Artefato sem avaliação acústica pt-BR aceita')
        model = (path.parent / data['model']).resolve()
        if model.stat().st_size > 256 * 1024 * 1024:
            raise ValueError('Detector excede o orçamento de 256 MiB')
        digest = hashlib.sha256()
        with model.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != data.get('sha256'):
            raise ValueError('Hash do detector acústico não confere')
        threshold = data.get('threshold', .8)
        if type(threshold) not in (float, int) or not 0 < threshold < 1:
            raise ValueError('Limiar acústico inválido')
        return cls(model, digest.hexdigest(), data['license'], threshold)


class OnnxWakeWordEngine:
    available = True

    def __init__(self, artifact, *, session_factory=None):
        if session_factory is None:
            import onnxruntime as ort
            ort.disable_telemetry_events()
            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            session_factory = lambda path: ort.InferenceSession(str(path), sess_options=options,
                providers=['CPUExecutionProvider'])
        self.session = session_factory(artifact.model)
        inputs = self.session.get_inputs()
        if len(inputs) != 1 or inputs[0].shape != [1, 16000] or inputs[0].type != 'tensor(float)':
            raise ValueError('Detector incompatível: esperado PCM float32 [1,16000]')
        self.input_name = inputs[0].name
        self.threshold = artifact.threshold
        self.reset()

    def reset(self):
        self.frames = deque()
        self.samples = 0
        self.since_check = 0

    def process(self, pcm):
        import numpy as np
        incoming = np.asarray(pcm, dtype=np.int16).reshape(-1)[-16000:].copy()
        self.frames.append(incoming)
        self.samples += len(incoming)
        self.since_check += len(incoming)
        while self.frames and self.samples - len(self.frames[0]) >= 16000:
            self.samples -= len(self.frames.popleft())
        if self.samples < 16000 or self.since_check < 1280:
            return False
        self.since_check = 0
        window = np.concatenate(self.frames)[-16000:].astype(np.float32).reshape(1, -1) / 32768
        score = np.asarray(self.session.run(None, {self.input_name: window})[0])
        if score.size != 1 or not np.isfinite(score).all() or not 0 <= float(score.reshape(-1)[0]) <= 1:
            raise ValueError('Probabilidade inválida no detector acústico')
        detected = float(score.reshape(-1)[0]) >= self.threshold
        if detected:
            self.reset()
        return detected
