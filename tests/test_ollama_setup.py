from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
from unittest import TestCase
from unittest.mock import patch

from jarvis.ollama_setup import SOURCE, binary, install, serve


class OllamaSetupTests(TestCase):
    def fixture(self, *, traversal=False):
        data = BytesIO()
        with tarfile.open(fileobj=data, mode='w') as archive:
            payload = b'#!/bin/sh\nexit 0\n'
            info = tarfile.TarInfo('../escape' if traversal else 'bin/ollama')
            info.size, info.mode = len(payload), 0o755
            archive.addfile(info, BytesIO(payload))
        archive = data.getvalue()
        release = {'tag_name': 'v1.2.3', 'assets': [{'name': 'ollama-linux-amd64.tar.zst',
            'digest': 'sha256:' + hashlib.sha256(archive).hexdigest(),
            'browser_download_url': SOURCE + '/releases/download/v1.2.3/ollama-linux-amd64.tar.zst'}]}
        return archive, release

    def test_checksum_install_and_reuse_without_network(self):
        archive, release = self.fixture()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'JARVIS_OLLAMA_DIR': directory}), \
                patch('jarvis.ollama_setup.platform.system', return_value='Linux'), \
                patch('jarvis.ollama_setup.platform.machine', return_value='x86_64'), \
                patch('jarvis.ollama_setup.urlopen', side_effect=[BytesIO(json.dumps(release).encode()), BytesIO(archive)]) as download, \
                patch('jarvis.ollama_setup._run'):
            first = install(progress=lambda _: None)
            second = install(progress=lambda _: None)
            self.assertFalse(first['reused'])
            self.assertTrue(second['reused'])
            self.assertEqual(download.call_count, 2)
            self.assertTrue(Path(binary()).is_file())
            manifest = json.loads((Path(directory) / 'runtime.json').read_text())
            self.assertEqual(manifest['archive_sha256'], hashlib.sha256(archive).hexdigest())

    def test_corrupt_download_and_archive_traversal_never_publish(self):
        for bad_hash, traversal in ((True, False), (False, True)):
            with self.subTest(hash=bad_hash, traversal=traversal):
                archive, release = self.fixture(traversal=traversal)
                if bad_hash: release['assets'][0]['digest'] = 'sha256:' + '0' * 64
                with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'JARVIS_OLLAMA_DIR': directory}), \
                        patch('jarvis.ollama_setup.platform.system', return_value='Linux'), \
                        patch('jarvis.ollama_setup.platform.machine', return_value='x86_64'), \
                        patch('jarvis.ollama_setup.urlopen', side_effect=[BytesIO(json.dumps(release).encode()), BytesIO(archive)]), \
                        patch('jarvis.ollama_setup._run') as run:
                    with self.assertRaises((ValueError, tarfile.FilterError)):
                        install(progress=lambda _: None)
                    self.assertFalse((Path(directory) / 'runtime.json').exists())
                    self.assertFalse((Path(directory) / 'escape').exists())
                    run.assert_not_called()

    def test_server_is_cpu_local_single_model_and_does_not_inherit_tokens(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                {'JARVIS_OLLAMA_DIR': directory, 'FCC_TOKEN': 'secret', 'OLLAMA_HOST': 'http://evil'}), \
                patch('jarvis.ollama_setup.binary', return_value='/fixture/ollama'), \
                patch('jarvis.ollama_setup._run') as run, patch('builtins.print'):
            serve('http://127.0.0.1:11434')
        env = run.call_args.kwargs['env']
        self.assertEqual(env['OLLAMA_NO_CLOUD'], '1')
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '-1')
        self.assertEqual(env['OLLAMA_MAX_LOADED_MODELS'], '1')
        self.assertEqual(env['OLLAMA_HOST'], 'http://127.0.0.1:11434')
        self.assertNotIn('FCC_TOKEN', env)
