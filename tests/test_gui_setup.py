import json
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

from jarvis.config import Config
from jarvis.gui import GuiBackend, JarvisWindow
from jarvis.gui_setup import run_setup, refresh
from jarvis.preferences import PreferenceStore


class SetupBackendTests(TestCase):
    def backend(self, root, factory=None):
        backend = GuiBackend(Config('http://127.0.0.1:1', '', 'private-token', root, root / 'db'),
                             service_factory=factory)
        backend.preference_store = PreferenceStore(root / 'preferences.json')
        backend.preferences = backend.preference_store.load()
        return backend

    def test_refresh_is_read_only_even_without_provider(self):
        with tempfile.TemporaryDirectory() as directory, patch('subprocess.Popen', side_effect=AssertionError('No worker')), \
                patch('socket.socket', side_effect=AssertionError('No network')):
            backend = self.backend(Path(directory))
            refresh(backend)
            self.assertEqual(backend.events.get_nowait()[0], 'setup_report')
            self.assertFalse(backend.preference_store.path.exists())

    def test_cancelled_queued_setup_updates_panel_without_installing(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory))
            backend.submit('setup_run', {'operation': 'ollama'})
            backend.cancel()
            with patch('jarvis.ollama_setup.install') as install:
                backend._process_command(*backend.local_commands.get_nowait())
            install.assert_not_called()
            results = [value for kind, value in list(backend.events.queue) if kind == 'setup_result']
            self.assertEqual(results[0]['state'], 'Cancelado')
            self.assertFalse(backend._action_pending.is_set())

    def test_engine_install_uses_latest_pointer_without_changing_selected_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory))
            with patch('jarvis.local_setup.install_engine', return_value={'state': 'OK', 'python': '/new/python'}) as install, \
                    patch('jarvis.local_setup.managed_python', return_value='/new/python'):
                run_setup(backend, {'operation': 'engine', 'python': '/selected/python', 'offline': True})
            self.assertTrue(install.call_args.kwargs['offline'])
            self.assertEqual(install.call_args.kwargs['python'], '/selected/python')
            self.assertEqual(backend.config.profile, 'fcc')
            self.assertFalse(backend.preference_store.path.exists())
            with patch('jarvis.local_setup.managed_python', return_value='/new/python'), \
                    patch.dict(os.environ, {}, clear=True), patch('jarvis.local_setup.check', return_value={'state': 'OK'}) as check:
                run_setup(backend, {'operation': 'check', 'model': 'fixture:1'})
            self.assertEqual(check.call_args.args[0].openjarvis_python, '/new/python')
            self.assertEqual(check.call_args.args[0].local_model, 'fixture:1')

    def test_error_and_cancellation_are_sanitized_and_preserve_preferences(self):
        from jarvis.cancellation import CancelledError
        for error in (OSError('https://private:token@host'), CancelledError('private speech')):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                backend = self.backend(Path(directory))
                with patch('jarvis.ollama_setup.install', side_effect=error):
                    run_setup(backend, {'operation': 'ollama'})
                events = list(backend.events.queue)
                result = next(payload for kind, payload in events if kind == 'setup_result')
                self.assertNotEqual(result['state'], 'OK')
                self.assertNotIn('private', json.dumps(events))
                self.assertNotIn('token@', json.dumps(events))
                self.assertFalse(backend.preference_store.path.exists())

    def test_progress_failure_retry_and_stop_work_while_fcc_is_blocked(self):
        from test_gui_backend import FakeService
        entered, release, installing, cancelled = (threading.Event() for _ in range(4))
        def connect(*args, **kwargs):
            entered.set()
            release.wait(5)
            return FakeService()
        def install(*, token, progress):
            progress('Etapa controlada em andamento')
            installing.set()
            while not token.cancelled:
                cancelled.wait(.01)
            cancelled.set()
            token.check()
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory), connect)
            backend.start()
            try:
                self.assertTrue(entered.wait(2))
                with patch('jarvis.ollama_setup.install', side_effect=install):
                    self.assertTrue(backend.submit('setup_run', {'operation': 'ollama'}))
                    self.assertTrue(installing.wait(2))
                    self.assertFalse(backend.submit('setup_run', {'operation': 'engine'}))
                    backend.cancel()
                    events = []
                    while ('busy', False) not in events:
                        events.append(backend.events.get(timeout=2))
                self.assertTrue(cancelled.is_set())
                self.assertIn(('setup_status', 'Etapa controlada em andamento'), events)
                self.assertTrue(any(k == 'setup_result' and p['state'] == 'Cancelado' for k, p in events))
                self.assertIsNone(backend.service)
                with patch('jarvis.ollama_setup.install', return_value={'state': 'OK'}):
                    self.assertTrue(backend.submit('setup_run', {'operation': 'ollama'}))
                    events = []
                    while ('busy', False) not in events:
                        events.append(backend.events.get(timeout=2))
                self.assertTrue(any(k == 'setup_result' and p['state'] == 'OK' for k, p in events))
            finally:
                backend.close()
                release.set()
                backend._thread.join(2)
                backend._local_thread.join(2)
            self.assertFalse(backend._local_thread.is_alive())

    def test_stt_and_server_operations_use_existing_adapters_without_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory))
            backend._ollama_session = Mock()
            backend._ollama_session.start.return_value = {'state': 'OK', 'managed': False}
            with patch('jarvis.local_setup.install_stt', return_value={'state': 'OK'}) as install:
                run_setup(backend, {'operation': 'stt', 'stt_model': 'small'})
            install.assert_called_once()
            run_setup(backend, {'operation': 'server'})
            run_setup(backend, {'operation': 'stop_server'})
            backend._ollama_session.start.assert_called_once()
            backend._ollama_session.close.assert_called_once()
            self.assertEqual(backend.preferences.inference_profile, 'fcc')

    def test_saved_local_session_starts_server_without_installing_and_closes_its_owner(self):
        from dataclasses import replace
        from test_gui_backend import FakeService
        with tempfile.TemporaryDirectory() as directory:
            backend = self.backend(Path(directory), lambda *a, **k: FakeService())
            backend.config = replace(backend.config, profile='local')
            backend._ollama_session = Mock()
            self.assertFalse(backend._local_thread.daemon)
            with patch('jarvis.local_setup.install_engine', side_effect=AssertionError('No startup install')), \
                    patch('jarvis.ollama_setup.install', side_effect=AssertionError('No startup download')):
                backend.start()
                try:
                    events = []
                    while not any(k == 'connected' for k, _ in events):
                        events.append(backend.events.get(timeout=2))
                    backend._ollama_session.start.assert_called_once()
                finally:
                    backend.close()
                    backend._thread.join(2)
                    backend._local_thread.join(2)
            backend._ollama_session.close.assert_called_once()


@skipUnless(os.getenv('DISPLAY'), 'Display gráfico indisponível')
class SetupWindowTests(TestCase):
    def test_setup_scroll_status_buttons_and_voice_navigation(self):
        backend = Mock(config=None)
        backend.events = queue.Queue()
        root = tk.Tk()
        root.tk.call('tk', 'scaling', 1.8)
        try:
            window = JarvisWindow(root, backend)
            root.geometry('1040x640')
            window._toggle_settings()
            window.workspace_panels.select(window.setup_panel_index)
            root.update()
            window.setup_model.set('fixture:1')
            start = next(b for b in window.setup_buttons if b['text'] == 'Iniciar servidor Local')
            start.invoke()
            self.assertEqual(backend.submit.call_args.args[1]['operation'], 'server')
            self.assertEqual(backend.submit.call_args.args[1]['model'], 'fixture:1')
            window._handle('busy', True)
            self.assertEqual(str(start['state']), 'disabled')
            self.assertEqual(str(window.setup_cancel_button['state']), 'normal')
            window.setup_cancel_button.invoke()
            backend.cancel.assert_called_once()
            window._handle('setup_result', {'state': 'Falhou', 'message': 'Falha controlada'})
            window._handle('busy', False)
            self.assertIn('Falhou', window.setup_status.get())
            self.assertEqual(str(start['state']), 'normal')
            window.setup_cancel_button.focus_force()
            root.update()
            canvas = window.setup_panel.canvas
            self.assertGreaterEqual(window.setup_cancel_button.winfo_rooty(), canvas.winfo_rooty())
            self.assertLess(window.setup_cancel_button.winfo_rooty() + window.setup_cancel_button.winfo_height(),
                            canvas.winfo_rooty() + canvas.winfo_height() + 2)
            link = next(b for b in window.setup_buttons if b['text'] == 'Configurar e testar microfone e voz')
            link.invoke()
            self.assertEqual(window.workspace_panels.selected, window.voice_panel_index)
        finally:
            root.destroy()

    def test_real_event_loop_remains_responsive_during_setup_failure_and_retry(self):
        from test_gui_backend import FakeService
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'JARVIS_GUI_VOICE': '0', 'JARVIS_PREFERENCES': str(Path(directory) / 'preferences.json')}):
            backend = GuiBackend(Config('http://127.0.0.1:1', '', '', Path(directory), Path(directory) / 'db'),
                                 service_factory=lambda *a, **k: FakeService())
            root = tk.Tk()
            errors = []
            root.report_callback_exception = lambda *args: errors.append(args)
            def pump_until(predicate):
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    root.update()
                    if predicate(): return
                    time.sleep(.01)
                self.fail('Interface não concluiu etapa no prazo')
            try:
                window = JarvisWindow(root, backend)
                control = next(b for b in window.setup_buttons if b['text'] == 'Instalar Ollama')
                with patch('jarvis.ollama_setup.install', side_effect=[OSError('private-token'), {'state': 'OK'}]):
                    control.invoke()
                    pump_until(lambda: 'Falhou' in window.setup_status.get() and str(control['state']) == 'normal')
                    control.invoke()
                    pump_until(lambda: window.setup_status.get().startswith('OK') and str(control['state']) == 'normal')
                self.assertNotIn('private-token', window.chat.get('1.0', 'end'))
                self.assertEqual(errors, [])
                self.assertFalse(backend.preference_store.path.exists())
            finally:
                backend.close()
                backend._thread.join(2)
                backend._local_thread.join(2)
                root.destroy()
