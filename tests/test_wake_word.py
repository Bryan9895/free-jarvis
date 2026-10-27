import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from jarvis.wake_word import WakeArtifact, OnnxWakeWordEngine
from jarvis.capture import CaptureCoordinator
from jarvis.latency import TurnTrace


class WakeWordTests(unittest.TestCase):
    def test_artifact_requires_isolated_keyword_hash_license_and_evaluation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            model = root / 'wake.onnx'
            model.write_bytes(b'fixture-only-not-a-model')
            data = {'version': 1, 'keyword': 'jarvis', 'language': 'pt-BR',
                    'format': 'pcm_float32_16000', 'license': 'fixture', 'model': model.name,
                    'sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
                    'evaluation': {'calls': 20, 'correct': 18, 'negative_minutes': 30,
                                   'false_activations': 1, 'evidence': 'synthetic-test-only'}}
            path = root / 'manifest.json'
            path.write_text(json.dumps(data))
            self.assertEqual(WakeArtifact.load(path).model, model)
            for change in ({'keyword': 'hey_jarvis'}, {'license': ''}, {'sha256': 'bad'}, {'evaluation': {}}):
                with self.subTest(change=change):
                    path.write_text(json.dumps({**data, **change}))
                    with self.assertRaises(ValueError): WakeArtifact.load(path)

    def test_onnx_contract_window_threshold_and_reset_without_claiming_accuracy(self):
        import numpy as np
        session = Mock()
        session.get_inputs.return_value = [SimpleNamespace(name='pcm', shape=[1, 16000], type='tensor(float)')]
        session.run.return_value = [np.array([[.9]])]
        engine = OnnxWakeWordEngine(WakeArtifact(Path('/tmp/fixture'), '', 'fixture', .8),
                                   session_factory=lambda _: session)
        for _ in range(12): self.assertFalse(engine.process(np.ones(1280, dtype=np.int16)))
        self.assertTrue(engine.process(np.ones(1280, dtype=np.int16)))
        array = session.run.call_args.args[1]['pcm']
        self.assertEqual(array.shape, (1, 16000))
        self.assertEqual(array.dtype, np.float32)
        self.assertEqual(engine.samples, 0)
        session.run.return_value = [np.array([[.1]])]
        for _ in range(100): self.assertFalse(engine.process(np.ones(1280, dtype=np.int16)))
        self.assertLess(engine.samples, 16000 + 1280)

    def test_capture_event_ids_and_output_ownership(self):
        coordinator = CaptureCoordinator()
        trace = TurnTrace()
        seen = []
        coordinator.transition(trace, 'ouvindo', 'VAD', seen.append)
        self.assertEqual(seen[0].turn_id, trace.turn_id)
        self.assertEqual(seen[0].session_id, trace.session_id)
        from threading import Event
        with coordinator.output(Event()):
            self.assertFalse(coordinator.lock.acquire(blocking=False))
        self.assertTrue(coordinator.lock.acquire(blocking=False))
        coordinator.lock.release()
