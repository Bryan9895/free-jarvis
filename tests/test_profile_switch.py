import os
from pathlib import Path
from queue import Queue
from threading import Lock
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from jarvis.config import Config
from jarvis.preferences import Preferences
from jarvis.profile_switch import switch_profile


class ProfileSwitchTests(TestCase):
    def backend(self):
        old = Mock()
        old._lock = Lock()
        old.toolkit.capabilities.enabled = {'files'}
        candidate = Mock()
        candidate.client.active_model = 'ollama/gemma4:e2b'
        candidate.toolkit.capabilities.enabled = {'files'}
        store = Mock(error=None)
        store.load.return_value = Preferences()
        backend = SimpleNamespace(service=old, config=Config('http://localhost', '', '', Path('/tmp'), Path('/tmp/db')),
            preferences=Preferences(), preference_store=store, authorization_store=object(),
            service_factory=Mock(return_value=candidate), auto=True, _approve=Mock(), events=Queue())
        return backend, old, candidate

    def test_success_keeps_authorizations_and_does_not_close_old_until_save(self):
        backend, old, candidate = self.backend()
        backend.preference_store.save.side_effect = lambda _: self.assertFalse(old.close.called)
        with patch.dict(os.environ, {}, clear=True):
            switch_profile(backend, {'profile': 'local'})
        self.assertIs(backend.service, candidate)
        self.assertIs(candidate.approval, old.approval)
        self.assertIs(candidate.toolkit.approve, old.approval)
        self.assertEqual(backend.config.profile, 'local')
        old.close.assert_called_once()

    def test_failed_prepare_or_persist_leaves_old_session_selected(self):
        for stage in ('prepare', 'persist'):
            with self.subTest(stage=stage):
                backend, old, candidate = self.backend()
                if stage == 'prepare':
                    backend.service_factory.side_effect = RuntimeError('Unavailable')
                else:
                    backend.preference_store.save.side_effect = OSError('Disk full')
                with patch.dict(os.environ, {}, clear=True), self.assertRaises((RuntimeError, OSError)):
                    switch_profile(backend, {'profile': 'local'})
                self.assertIs(backend.service, old)
                old.close.assert_not_called()
                if stage == 'persist': candidate.close.assert_called_once()

    def test_explicit_environment_and_active_turn_block_switch(self):
        backend, old, candidate = self.backend()
        with patch.dict(os.environ, {'JARVIS_PROFILE': 'fcc'}), self.assertRaises(ValueError):
            switch_profile(backend, {'profile': 'local'})
        with old._lock, patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            switch_profile(backend, {'profile': 'local'})
        backend.service_factory.assert_not_called()

    def test_switching_model_within_profile_preserves_disabled_capabilities(self):
        backend, old, candidate = self.backend()
        candidate.toolkit.registry.capabilities = {'files', 'desktop'}
        with patch.dict(os.environ, {}, clear=True):
            switch_profile(backend, {'profile': 'fcc', 'model': 'configured'})
        self.assertEqual(candidate.toolkit.capabilities.enabled, {'files'})

