import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from time import monotonic
import unittest
from unittest.mock import patch

from jarvis.cancellation import CancellationToken, CancelledError
from jarvis.config import Config
from jarvis.local_provider import OPENJARVIS_REVISION
from jarvis.local_setup import (SOURCE, REQUIREMENT, _run, _publish, install_engine,
                               managed_python, status, _installation_lock)

INFO = {'revision': OPENJARVIS_REVISION, 'engine': 'ollama',
        'package_version': 'fixture', 'python_version': [3, 13, 0], 'inference': 'Não testado'}


class LocalSetupTests(unittest.TestCase):
    def installed(self, root, name='previous'):
        python = root / 'versions' / name / 'bin/python'
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text('#!/bin/sh\nexit 0\n')
        python.chmod(0o755)
        _publish(root, {'version': 1, 'revision': OPENJARVIS_REVISION,
                        'source': SOURCE, 'python': str(python)})
        return python

    def installer(self, commands, *, fail_stage=''):
        def run(command, *, stage, **kwargs):
            commands.append((command, stage))
            if stage == fail_stage:
                raise RuntimeError('Controlled failure')
            if stage == 'Verificar Python':
                return '3.13'
            if stage == 'Criar ambiente':
                destination = Path(command[-1])
                python = destination / 'bin/python'
                python.parent.mkdir(parents=True)
                python.write_text('#!/bin/sh\nexit 0\n')
                python.chmod(0o755)
            return ''
        return run

    def test_verified_install_publishes_pointer_and_reuses_without_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root, commands = Path(directory), []
            with patch('jarvis.local_setup.shutil.which', return_value='/usr/bin/uv'), \
                    patch('jarvis.local_setup._run', side_effect=self.installer(commands)), \
                    patch('jarvis.local_setup.inspect_runtime', return_value=INFO):
                first = install_engine(root=root, python='/python3.13', offline=True, progress=lambda _: None)
                count = len(commands)
                second = install_engine(root=root, python='/python3.13', offline=True, progress=lambda _: None)
            self.assertFalse(first['reused'])
            self.assertTrue(second['reused'])
            self.assertEqual(len(commands), count)
            self.assertEqual(managed_python(root), first['python'])
            pip_command = next(command for command, stage in commands if stage == 'Instalar OpenJarvis')
            self.assertIn('--offline', pip_command)
            self.assertIn(REQUIREMENT, pip_command)
            # The installed path is final from creation onward; no moving a venv.
            self.assertEqual(commands[1][0][-1], str(Path(first['python']).parents[1]))

    def test_failed_update_keeps_old_manifest_and_cleans_only_new_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = self.installed(root)
            before = (root / 'runtime.json').read_bytes()
            commands = []
            with patch('jarvis.local_setup.shutil.which', return_value='/usr/bin/uv'), \
                    patch('jarvis.local_setup.inspect_runtime', side_effect=RuntimeError('old invalid')), \
                    patch('jarvis.local_setup._run', side_effect=self.installer(commands, fail_stage='Instalar OpenJarvis')):
                with self.assertRaises(RuntimeError):
                    install_engine(root=root, python='/python3.13', progress=lambda _: None)
            self.assertEqual((root / 'runtime.json').read_bytes(), before)
            self.assertTrue(old.is_file())
            self.assertEqual(list((root / 'versions').iterdir()), [old.parents[1]])

    def test_rejected_revision_never_publishes_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('jarvis.local_setup.shutil.which', return_value='/usr/bin/uv'), \
                    patch('jarvis.local_setup._run', side_effect=self.installer([])), \
                    patch('jarvis.local_setup.inspect_runtime', return_value={**INFO, 'revision': 'wrong'}):
                with self.assertRaises(ValueError):
                    install_engine(root=root, python='/python3.13', progress=lambda _: None)
            self.assertFalse((root / 'runtime.json').exists())
            self.assertEqual(list((root / 'versions').iterdir()), [])

    def test_publication_failure_preserves_previous_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = self.installed(root)
            before = (root / 'runtime.json').read_bytes()
            with patch('jarvis.local_setup.shutil.which', return_value='/usr/bin/uv'), \
                    patch('jarvis.local_setup._run', side_effect=self.installer([])), \
                    patch('jarvis.local_setup.inspect_runtime', side_effect=[RuntimeError('old failed'), INFO]), \
                    patch('jarvis.local_setup._publish', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    install_engine(root=root, python='/python3.13', progress=lambda _: None)
            self.assertEqual((root / 'runtime.json').read_bytes(), before)
            self.assertEqual(list((root / 'versions').iterdir()), [old.parents[1]])

    def test_second_installer_can_be_cancelled_while_waiting_for_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _installation_lock(root, CancellationToken()):
                token = CancellationToken(deadline=monotonic() + .1)
                with self.assertRaises(TimeoutError):
                    install_engine(root=root, cancel_token=token, progress=lambda _: None)
            self.assertFalse((root / 'versions').exists())

    def test_cancelled_install_reaps_process_and_removes_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root, token = Path(directory), CancellationToken()
            original = self.installer([])
            def run(command, *, stage, **kwargs):
                result = original(command, stage=stage, **kwargs)
                if stage == 'Instalar OpenJarvis':
                    token.cancel()
                return result
            with patch('jarvis.local_setup.shutil.which', return_value='/usr/bin/uv'), \
                    patch('jarvis.local_setup._run', side_effect=run), \
                    patch('jarvis.local_setup.inspect_runtime', side_effect=lambda *a, **k: (token.check(), INFO)[1]):
                with self.assertRaises(CancelledError):
                    install_engine(root=root, python='/python3.13', cancel_token=token, progress=lambda _: None)
            self.assertEqual(list((root / 'versions').iterdir()), [])
            self.assertFalse((root / 'runtime.json').exists())

    def test_incompatible_python_fails_before_creating_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('jarvis.local_setup.shutil.which', return_value='/usr/bin/uv'), \
                    patch('jarvis.local_setup._run', return_value='3.14') as run:
                with self.assertRaises(ValueError):
                    install_engine(root=root, python='/python3.14', progress=lambda _: None)
            self.assertEqual(run.call_count, 1)
            self.assertFalse((root / 'versions').exists())

    def test_startup_reads_pointer_without_spawning_and_explicit_env_wins(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'JARVIS_LOCAL_RUNTIME_DIR': directory, 'JARVIS_PREFERENCES': directory + '/prefs.json'}, clear=True):
            python = self.installed(Path(directory))
            with patch('subprocess.Popen') as spawn:
                self.assertEqual(Config.from_env().openjarvis_python, str(python))
                spawn.assert_not_called()
                with patch.dict(os.environ, {'JARVIS_OPENJARVIS_PYTHON': '/explicit/python'}):
                    self.assertEqual(Config.from_env().openjarvis_python, '/explicit/python')

    def test_status_never_queries_models_or_opens_capture(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
                patch('jarvis.local_setup.shutil.which', return_value=None), \
                patch('jarvis.local_provider.OpenJarvisProvider.initialize') as initialize:
            report = status(root=directory)
            self.assertEqual(report['engine']['state'], 'Falta')
            self.assertEqual(report['inference']['state'], 'Não testado')
            initialize.assert_not_called()

    def test_malformed_or_outside_pointer_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for data in ([], None, {'version': 1, 'source': SOURCE, 'revision': OPENJARVIS_REVISION,
                                    'python': sys.executable}, {'python': '../invalid'}):
                (root / 'runtime.json').write_text(json.dumps(data))
                self.assertEqual(managed_python(root), '')

    def test_installer_timeout_cancels_real_process_without_leaking_output(self):
        started = monotonic()
        token = CancellationToken(deadline=monotonic() + .15)
        with self.assertRaises(TimeoutError):
            _run([sys.executable, '-c', 'import time; print("private"); time.sleep(30)'],
                 stage='fixture', token=token)
        self.assertLess(monotonic() - started, 3)
        with self.assertRaisesRegex(RuntimeError, 'código 1') as error:
            _run([sys.executable, '-c', 'print("secret credential"); raise SystemExit(1)'],
                 stage='fixture', token=CancellationToken())
        self.assertNotIn('secret', str(error.exception))
