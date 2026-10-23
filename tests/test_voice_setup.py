import hashlib
import io
import json
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch
from jarvis import voice_setup as setup
from jarvis.cancellation import CancelledError


class VoiceSetupTests(unittest.TestCase):
    def fixtures(self):
        files = {setup.NAME + '.onnx': b'controlled fixture, not a model',
                 setup.NAME + '.onnx.json': json.dumps({'language': {'code': 'pt_BR'}, 'audio': {'sample_rate': 22050}}).encode(),
                 'MODEL_CARD': b'Dataset License: CC0'}
        manifest = {name: (hashlib.sha256(data).hexdigest(), 10000) for name, data in files.items()}
        def download(url, timeout):
            data = files[url.rsplit('/', 1)[-1]]
            response = io.BytesIO(data)
            response.headers = {'Content-Length': str(len(data))}
            return response
        return manifest, download

    def test_download_verify_atomic_install_and_reuse(self):
        manifest, download = self.fixtures()
        with tempfile.TemporaryDirectory() as td, patch.object(setup, 'FILES', manifest), patch.object(setup, 'urlopen', side_effect=download) as request:
            progress = []
            model = setup.install_faber(root=td, cancel=Event(), progress=progress.append)
            self.assertTrue(model.is_file())
            self.assertTrue((model.parent / 'MODEL_CARD').is_file())
            self.assertTrue((model.parent / 'SOURCE.json').is_file())
            self.assertEqual(request.call_count, 3)
            self.assertEqual(setup.install_faber(root=td, cancel=Event()), model)
            self.assertEqual(request.call_count, 3)
            self.assertEqual(list(Path(td).iterdir()), [model.parent])
            self.assertIn('verificada', progress[-1])

    def test_hash_mismatch_does_not_publish_partial_voice(self):
        manifest, download = self.fixtures()
        manifest[setup.NAME + '.onnx'] = ('0' * 64, 10000)
        with tempfile.TemporaryDirectory() as td, patch.object(setup, 'FILES', manifest), patch.object(setup, 'urlopen', side_effect=download):
            with self.assertRaisesRegex(ValueError, 'Hash'):
                setup.install_faber(root=td, cancel=Event())
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_network_failure_and_cancel_remove_staging(self):
        manifest, download = self.fixtures()
        with tempfile.TemporaryDirectory() as td, patch.object(setup, 'FILES', manifest), patch.object(setup, 'urlopen', side_effect=OSError('rede')):
            with self.assertRaises(OSError):
                setup.install_faber(root=td, cancel=Event())
            self.assertEqual(list(Path(td).iterdir()), [])
        cancel = Event()
        with tempfile.TemporaryDirectory() as td, patch.object(setup, 'FILES', manifest), patch.object(setup, 'urlopen', side_effect=download):
            with self.assertRaises(CancelledError):
                setup.install_faber(root=td, cancel=cancel, progress=lambda _: cancel.set())
            self.assertEqual(list(Path(td).iterdir()), [])
