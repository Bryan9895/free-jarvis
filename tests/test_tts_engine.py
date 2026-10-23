from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch
import unittest
from jarvis.tts_engine import PiperSynthesizer
from jarvis.cancellation import CancelledError


class PiperWorkerTests(unittest.TestCase):
    def backend(self):
        context, parent, child, process = Mock(), Mock(), Mock(), Mock()
        process.pid = 123
        context.Pipe.return_value = parent, child
        context.Process.return_value = process
        parent.poll.return_value = True
        parent.recv.return_value = None
        return context, parent, child, process

    def test_one_resident_worker_for_sequential_chunks(self):
        context, parent, child, process = self.backend()
        engine = PiperSynthesizer()
        with patch('jarvis.tts_engine.multiprocessing.get_context', return_value=context):
            engine.synthesize('/tmp/model.onnx', 'primeiro', '/tmp/1.wav', Event())
            engine.synthesize('/tmp/model.onnx', 'segundo', '/tmp/2.wav', Event())
        process.start.assert_called_once()
        child.close.assert_called_once()
        self.assertEqual(parent.send.call_args_list[0].args[0][0], 'primeiro')
        self.assertEqual(parent.send.call_args_list[1].args[0][0], 'segundo')
        engine.close()

    def test_cancellation_kills_worker_and_invalidates_connection(self):
        context, parent, child, process = self.backend()
        cancel = Event()
        parent.poll.side_effect = lambda _: (cancel.set(), False)[1]
        engine = PiperSynthesizer()
        with patch('jarvis.tts_engine.multiprocessing.get_context', return_value=context):
            with self.assertRaises(CancelledError):
                engine.synthesize('/tmp/model.onnx', 'frase', '/tmp/1.wav', cancel)
        process.terminate.assert_called_once()
        self.assertIsNone(engine._process)
        self.assertIsNone(engine._connection)

    def test_invalid_voice_error_closes_worker_and_can_recover(self):
        context, parent, child, process = self.backend()
        parent.recv.side_effect = ['FileNotFoundError: config', None]
        engine = PiperSynthesizer()
        with patch('jarvis.tts_engine.multiprocessing.get_context', return_value=context):
            with self.assertRaisesRegex(RuntimeError, 'config'):
                engine.synthesize('/tmp/model.onnx', 'frase', '/tmp/1.wav', Event())
            self.assertIsNone(engine._process)
            engine.synthesize('/tmp/model.onnx', 'nova frase', '/tmp/2.wav', Event())
        self.assertEqual(process.start.call_count, 2)
        engine.close()

    def test_timeout_reaps_worker(self):
        context, parent, child, process = self.backend()
        engine = PiperSynthesizer()
        with patch('jarvis.tts_engine.multiprocessing.get_context', return_value=context):
            with self.assertRaisesRegex(RuntimeError, 'Tempo limite'):
                engine.synthesize('/tmp/model.onnx', 'frase', '/tmp/1.wav', Event(), timeout=0)
        self.assertIsNone(engine._process)
        process.close.assert_called_once()
