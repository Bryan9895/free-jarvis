import os
from pathlib import Path
import queue
import tempfile
import threading
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

from jarvis.config import Config
from jarvis.gui import GuiBackend, JarvisWindow
from jarvis.gui_comparison import dispatch


class ComparisonBackendTests(TestCase):
    def test_cancel_while_fcc_connects_keeps_partial_result_and_profile(self):
        from test_gui_backend import FakeService
        entered, release, measuring = (threading.Event() for _ in range(3))
        def connect(*args, **kwargs):
            entered.set()
            release.wait(5)
            return FakeService()
        def evaluate(config, models, *, directory, cancel_token, progress, **kwargs):
            self.assertEqual(config.profile, 'fcc')  # Comparison forces Local internally, not in the live session.
            progress({'model': models[0], 'scenario': 'short_question', 'phase': 'warm', 'completed': 1, 'expected': 30})
            measuring.set()
            while not cancel_token.cancelled: threading.Event().wait(.01)
            return Path(directory), {'state': 'cancelled', 'models': {}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = GuiBackend(Config('http://127.0.0.1:1', '', '', root, root / 'db'), service_factory=connect)
            backend._ollama_session = Mock()
            backend._ollama_session.monitor_pid.return_value = os.getpid()
            backend.start()
            try:
                self.assertTrue(entered.wait(2))
                with patch('jarvis.model_evaluation.evaluate', side_effect=evaluate):
                    backend.submit('comparison_run', {'directory': directory, 'models': ['first:1', 'second:1'], 'pid': ''})
                    self.assertTrue(measuring.wait(2))
                    self.assertFalse(backend.submit('setup_run', {'operation': 'server'}))
                    backend.cancel()
                    events = []
                    while ('busy', False) not in events: events.append(backend.events.get(timeout=2))
                self.assertTrue(any(kind == 'comparison_report' and value['state'] == 'cancelled' for kind, value in events))
                self.assertTrue(any(kind == 'comparison_status' and 'cancelada' in value for kind, value in events))
                self.assertIsNone(backend.service)
                self.assertEqual(backend.config.profile, 'fcc')
            finally:
                backend.close()
                release.set()
                backend._thread.join(2)
                backend._local_thread.join(2)

    def test_changed_live_weights_cannot_be_copied_as_approved_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = GuiBackend(Config('http://127.0.0.1:1', '', '', root, root / 'db'))
            with patch('jarvis.model_evaluation.approved_model', return_value=('first:1', {'digest': 'expected'})), \
                    patch('jarvis.local_provider.OpenJarvisProvider') as factory:
                factory.return_value._exchange.return_value = {'digest': 'changed'}
                dispatch(backend, 'comparison_pick', {'directory': directory})
            self.assertFalse(any(kind == 'comparison_pick' for kind, value in list(backend.events.queue)))
            self.assertEqual(backend.config.profile, 'fcc')
            factory.return_value.close.assert_called_once()


@skipUnless(os.getenv('DISPLAY'), 'Display gráfico indisponível')
class ComparisonWindowTests(TestCase):
    def window(self):
        backend = Mock(config=None)
        backend.events = queue.Queue()
        root = tk.Tk()
        return root, backend, JarvisWindow(root, backend)

    def test_review_requires_explicit_counts_and_pick_only_fills_configuration(self):
        root, backend, window = self.window()
        try:
            window._handle('comparison_report', {'directory': '/tmp/private-fixture', 'state': 'completed',
                'models': [{'name': name, 'turns': 2, 'p95': 1, 'pss_kib': 100} for name in ('first:1', 'second:1')]})
            control = next(button for button in window.comparison_buttons if button['text'] == 'Registrar revisão e indicar elegível')
            backend.submit.reset_mock()
            control.invoke()
            backend.submit.assert_not_called()
            self.assertIn('Preencha', window.comparison_status.get())
            for fields in window.comparison_assessments.values():
                for key, variable in fields.items(): variable.set('2' if key in ('reviewed', 'adequate') else '0')
            control.invoke()
            command, value = backend.submit.call_args.args
            self.assertEqual(command, 'comparison_review')
            self.assertEqual(value['assessments']['first:1']['adequate'], 2)
            window._handle('comparison_pick', 'first:1')
            self.assertEqual(window.setup_model.get(), 'first:1')
            self.assertEqual(window.workspace_panels.selected, window.setup_panel_index)
            self.assertEqual(backend.submit.call_args.args[0], 'comparison_review')
        finally:
            root.destroy()

    def test_stop_stays_accessible_at_large_scale_and_private_replies_stay_out_of_chat(self):
        root, backend, window = self.window()
        root.tk.call('tk', 'scaling', 1.8)
        try:
            root.geometry('1040x640')
            window._toggle_settings()
            window.workspace_panels.select(window.comparison_panel_index)
            window._handle('busy', True)
            self.assertTrue(all(str(button['state']) == 'disabled' for button in window.comparison_buttons))
            self.assertEqual(str(window.comparison_cancel['state']), 'normal')
            window.comparison_cancel.focus_force()
            root.update()
            canvas = window.comparison_panel.canvas
            self.assertGreaterEqual(window.comparison_cancel.winfo_rooty(), canvas.winfo_rooty())
            self.assertLess(window.comparison_cancel.winfo_rooty() + window.comparison_cancel.winfo_height(),
                            canvas.winfo_rooty() + canvas.winfo_height() + 2)
            window.comparison_cancel.invoke()
            backend.cancel.assert_called_once()
            window._handle('comparison_responses', [{'model': 'first:1', 'phase': 'warm', 'scenario': 'short_question',
                'state': 'passed', 'request': 'directed request', 'answer': 'privateX directed answer'}])
            self.assertNotIn('privateX', window.chat.get('1.0', 'end'))
            self.assertTrue(any(isinstance(widget, tk.Toplevel) for widget in root.winfo_children()))
        finally:
            root.destroy()
