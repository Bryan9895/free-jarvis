import os
import queue
import unittest
import tkinter as tk
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from jarvis.gui import JarvisWindow
from jarvis.tools import DEFAULT_REGISTRY


@unittest.skipUnless(os.getenv('DISPLAY'), 'Display gráfico indisponível')
class WindowTests(unittest.TestCase):
    def test_destroy_during_event_handling_does_not_rearm_poll(self):
        backend = Mock()
        backend.events = queue.Queue()
        root = tk.Tk()
        window = JarvisWindow(root, backend)
        root.after_cancel(window._poll_timer)
        window._poll_timer = None
        backend.events.put(('test_close', None))
        with patch.object(window, '_handle', side_effect=lambda *_: root.destroy()):
            window._poll()
        self.assertTrue(window._destroyed)
        self.assertIsNone(window._poll_timer)

    def test_select_save_install_failure_and_retry_with_real_event_loop(self):
        from jarvis.gui import GuiBackend
        from jarvis.preferences import PreferenceStore
        from test_gui_backend import FakeService
        release, entered = threading.Event(), threading.Event()
        def connect(*_args, **_kwargs):
            entered.set()
            release.wait()
            return FakeService()
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {
                'JARVIS_GUI_VOICE': '0', 'JARVIS_PREFERENCES': str(Path(td) / 'preferences.json')}):
            backend = GuiBackend(None, service_factory=connect)
            root = tk.Tk()
            errors = []
            root.report_callback_exception = lambda *args: errors.append(args)
            def pump_until(predicate):
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(.01)
                self.fail('A interface não confirmou a operação dentro do prazo')
            try:
                window = JarvisWindow(root, backend)
                self.assertTrue(entered.wait(2))
                selected, installed = Path(td) / 'selected.onnx', Path(td) / 'installed.onnx'
                with patch('jarvis.gui.filedialog.askopenfilename', return_value=str(selected)) as picker:
                    window.voice_select_button.invoke()
                picker.assert_called_once()
                self.assertIs(picker.call_args.kwargs['parent'], root)
                self.assertEqual(window.voice_piper_model.get(), str(selected))
                backend.events.put(('voice_capture_level', {'dbfs': -30}))
                window.voice_mode.set('manual')
                window.voice_save_button.invoke()
                pump_until(lambda: 'Preferências salvas' in window.voice_status.get() and not backend._action_pending.is_set())
                self.assertEqual(PreferenceStore().load().piper_model, str(selected))
                with patch('jarvis.voice_setup.install_faber', side_effect=[OSError('rede indisponível'), installed]):
                    window.voice_install_button.invoke()
                    pump_until(lambda: 'rede indisponível' in window.chat.get('1.0', 'end') and str(window.voice_install_button['state']) == 'normal')
                    window.voice_install_button.invoke()
                    pump_until(lambda: window.voice_piper_model.get() == str(installed) and str(window.voice_save_button['state']) == 'normal')
                self.assertEqual(PreferenceStore().load().piper_model, str(installed))
                self.assertIsNone(backend.service)
                self.assertEqual(errors, [])
                self.assertIsNotNone(window._poll_timer)
            finally:
                backend.close()
                release.set()
                backend._thread.join(2)
                backend._local_thread.join(2)
                root.destroy()

    def test_capture_level_without_elapsed_keeps_poll_and_buttons_alive(self):
        backend = Mock()
        backend.events = queue.Queue()
        root = tk.Tk()
        try:
            window = JarvisWindow(root, backend)
            root.after_cancel(window._poll_timer)
            window._poll_timer = None
            backend.events.put(('voice_capture_level', {'dbfs': -30}))
            backend.events.put(('voice_installed', '/tmp/voice.onnx'))
            backend.events.put(('busy', False))
            window._poll()
            self.assertEqual(float(window.voice_capture_level['value']), 50)
            self.assertNotIn('/6 s', window.voice_status.get())
            self.assertEqual(window.voice_piper_model.get(), '/tmp/voice.onnx')
            self.assertEqual(str(window.send_button['state']), 'normal')
            self.assertIsNotNone(window._poll_timer)
            self.assertTrue(backend.events.empty())
        finally:
            root.destroy()

    def test_bad_event_does_not_lose_save_confirmation_or_next_tick(self):
        backend = Mock()
        backend.events = queue.Queue()
        root = tk.Tk()
        try:
            window = JarvisWindow(root, backend)
            root.after_cancel(window._poll_timer)
            window._poll_timer = None
            backend.events.put(('voice_test_level', {}))
            backend.events.put(('voice_status', 'Preferências salvas.'))
            backend.events.put(('busy', False))
            window._poll()
            self.assertEqual(window.voice_status.get(), 'Preferências salvas.')
            self.assertIn('Falha ao atualizar', window.chat.get('1.0', 'end'))
            self.assertIsNotNone(window._poll_timer)
            self.assertTrue(backend.events.empty())
        finally:
            root.destroy()

    def test_voice_output_scroll_at_larger_scale(self):
        backend = Mock()
        backend.events = queue.Queue()
        root = tk.Tk()
        root.tk.call('tk', 'scaling', 1.8)
        try:
            window = JarvisWindow(root, backend)
            root.geometry('1040x640')
            window._toggle_settings()
            window.workspace_panels.select(len(window.workspace_panels.panels) - 1)
            window.voice_pages.select(window.voice_pages.tabs()[-1])
            root.update()
            viewport = window.voice_output_scroll.canvas
            self.assertLessEqual(viewport.winfo_rooty()+viewport.winfo_height(), root.winfo_rooty()+root.winfo_height())
            buttons = [widget for widget in window.voice_output_scroll.content.winfo_children()
                       if widget.winfo_class() == 'TButton']
            buttons[-1].focus_force()
            root.update()
            self.assertLessEqual(buttons[-1].winfo_rooty()+buttons[-1].winfo_height(),
                                 viewport.winfo_rooty()+viewport.winfo_height()+2)
        finally:
            root.destroy()

    def test_compact_layout_and_plan_controls(self):
        backend = Mock()
        backend.events = queue.Queue()
        backend.submit.return_value = True
        backend.service = SimpleNamespace(toolkit=SimpleNamespace(registry=DEFAULT_REGISTRY))
        root = tk.Tk()
        root.tk.call('tk', 'scaling', 1.3333)
        try:
            with patch.dict('os.environ', {'JARVIS_GUI_VOICE':'0'}):
                window = JarvisWindow(root, backend)
                root.geometry('1040x640')
                root.update()
                self.assertFalse(window._navigation.winfo_ismapped())
                self.assertFalse(window.workspace_panels.winfo_ismapped())
                window._toggle_settings()
                root.update()
                # A última página construída não pode esconder a página selecionada.
                self.assertEqual(window.workspace_panels.selected, 0)
                self.assertTrue(window.workspace_panels.panels[0].winfo_ismapped())
                self.assertFalse(window.workspace_panels.panels[-1].winfo_ismapped())
                window._handle('plan', {'status':'ready', 'steps':[
                    {'id':1,'description':'Organizar janelas','status':'pending'}]})
                root.update()
                for widget in (window.voice_quick, window.send_button, window.plan_detail_text):
                    self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),
                                         root.winfo_rooty()+root.winfo_height())
                window.plan_goal.insert(0, 'Organizar o ambiente')
                window._plan_action('prepare')
                backend.submit.assert_called_with('plan_action', ('prepare', 'Organizar o ambiente'))
                window._handle('plan_history', [{'id':3,'goal':'Plano salvo'}])
                window._select_plan()
                backend.submit.assert_called_with('plan_action', ('select',3))
                window.workspace_panels.buttons[-1].invoke()
                root.update()
                self.assertFalse(window.workspace_panels.panels[0].winfo_ismapped())
                self.assertTrue(window.workspace_panels.panels[-1].winfo_ismapped())
                window.voice_device.set('14: Bluetooth mic')
                window._voice_test_action('capture')
                backend.submit.assert_called_with('voice_test_capture', '14: Bluetooth mic')
                window._handle('voice_test_level', {'elapsed':2, 'dbfs':-30})
                self.assertEqual(float(window.voice_level['value']), 50)
                window._handle('voice_test_transcript', {
                    'model':'small', 'seconds':4, 'expected':'Olá Jarvis',
                    'recognized':'ola jarvis', 'comparison':{
                        'similarity_percent':100, 'word_edits':0, 'reference_words':2}})
                self.assertIn('Similaridade textual: 100%', window.voice_test_result.get('1.0', 'end'))
                window.voice_test_model.set('small')
                window._apply_voice_settings()
                backend.submit.assert_called_with('voice_listen_start', {
                    'device':'14: Bluetooth mic', 'model':'small'})
                window._handle('voice_status', 'Whisper small: Escuta contínua indisponível: desconectado')
                self.assertFalse(window.voice_listening)
                backend.finish_voice_turn.return_value = False
                window._push_to_talk()
                backend.submit.assert_called_with('voice_push_to_talk', {
                    'device':'14: Bluetooth mic', 'model':'small'})
                window._handle('models', ['openai/example', 'nvidia_nim/example'])
                window.model_filter.set('openai')
                self.assertEqual(tuple(window.models['values']), ('openai/example',))
                window._show_model('nvidia_nim/example')
                window.model_choice.set('openai/example')
                self.assertEqual(window.model.get(), 'nvidia_nim/example')
                with patch.dict('os.environ', {'JARVIS_GUI_VOICE':'1'}):
                    window._handle('connected', {'model':'openai/example', 'approval':'auto', 'capabilities':[]})
                backend.submit.assert_called_with('voice_listen_start', {
                    'device':'14: Bluetooth mic', 'model':'small'})
                window._handle('busy', True)
                window._handle('error', 'HTTP 404 em /v1/responses: NIM not found')
                window._handle('busy', False)
                self.assertIn('Modelos', window.chat.get('1.0', 'end'))
                self.assertEqual(window.hud.label, 'PEDIDO NÃO CONCLUÍDO')
                window.voice_status.set('Whisper small: Aguardando Jarvis; detecção e transcrição são locais…')
                root.update()
                panel = window.workspace_panels.panels[-1]
                for widget in panel.winfo_children():
                    if widget.winfo_ismapped():
                        self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),
                                             root.winfo_rooty()+root.winfo_height())
                def check_bounds(parent):
                    for widget in parent.winfo_children():
                        if widget.winfo_ismapped():
                            self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),
                                                 root.winfo_rooty()+root.winfo_height())
                            self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),
                                                 root.winfo_rootx()+root.winfo_width())
                            if not isinstance(widget, tk.Canvas):
                                check_bounds(widget)
                for page in window.voice_pages.tabs():
                    window.voice_pages.select(page)
                    root.update()
                    check_bounds(window.voice_pages)
                for geometry in ('1366x768', '1040x640'):
                    root.geometry(geometry)
                    root.update()
                    check_bounds(window.voice_pages)
                    window._toggle_settings()
                    root.update()
                    for widget in (window.voice_quick, window.send_button, window.push_to_talk_quick):
                        self.assertTrue(widget.winfo_ismapped())
                        self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), root.winfo_rootx()+root.winfo_width())
                    window._toggle_settings()
                    root.update()
                window.workspace_panels.select(window.models_panel_index)
                root.update()
                check_bounds(window.workspace_panels.panels[window.models_panel_index])
        finally:
            root.destroy()
