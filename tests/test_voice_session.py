import unittest
from unittest.mock import Mock
from jarvis.voice_session import run_voice_session


class VoiceSessionTests(unittest.TestCase):
    def run_session(self, service, voice, commands):
        state = Mock()
        class Listener:
            def __init__(self, voice, callback, status):
                self.callback = callback
                self.status = status
                self.pending = iter(commands)
            def start(self): self.callback(next(self.pending))
            def resume(self):
                state.resume()
                self.callback(next(self.pending))
            def stop(self): state.stop()
        reports = []
        run_voice_session(service, voice, report=reports.append, listener_factory=Listener)
        return state, reports

    def test_no_keyboard_required_and_tts_precedes_resume(self):
        service, voice = Mock(), Mock()
        service.ask.return_value = 'Olá'
        voice.speak.return_value = 'spoken'
        state, _ = self.run_session(service, voice, ['olá', 'sair', 'unused'])
        service.ask.assert_called_once_with('olá')
        voice.speak.assert_called_once_with('Olá')
        state.stop.assert_called_once()

    def test_failed_turn_resumes_listening(self):
        service, voice = Mock(), Mock()
        service.ask.side_effect = [RuntimeError('FCC offline'), 'Quatro']
        voice.speak.return_value = 'spoken'
        state, reports = self.run_session(service, voice, ['primeiro', 'segundo', 'sair', 'unused'])
        self.assertEqual(service.ask.call_count, 2)
        voice.speak.assert_called_once_with('Quatro')
        self.assertTrue(any('FCC offline' in line for line in reports))
        state.stop.assert_called_once()

    def test_microphone_failure_exits_instead_of_waiting_forever(self):
        state = Mock()
        class FailedListener:
            def __init__(self, voice, callback, status): self.status = status
            def start(self): self.status('Escuta contínua indisponível: sem microfone')
            def stop(self): state.stop()
        service = Mock()
        run_voice_session(service, Mock(), report=lambda _: None, listener_factory=FailedListener)
        service.ask.assert_not_called()
        state.stop.assert_called_once()


class MixedInputTests(unittest.TestCase):
    def test_voice_input_without_reading_keyboard(self):
        from jarvis.voice_session import MixedInput
        listener = Mock()
        entry = MixedInput(Mock(), report=lambda _: None,
                           listener_factory=lambda *_args: listener)
        entry.start()
        entry.commands.put('abra o Firefox')
        stdin = Mock()
        self.assertEqual(entry.read(stdin, ready=lambda: False), 'abra o Firefox')
        stdin.readline.assert_not_called()
        listener.pause.assert_called_once()
        entry.close()
        listener.stop.assert_called_once()

    def test_text_commands_preserved_and_eof_exits(self):
        from io import StringIO
        from jarvis.voice_session import MixedInput
        listener = Mock()
        entry = MixedInput(Mock(), report=lambda _: None,
                           listener_factory=lambda *_args: listener)
        stream = StringIO('/modelos\n')
        self.assertEqual(entry.read(stream, ready=lambda: True), '/modelos')
        with self.assertRaises(EOFError):
            entry.read(stream, ready=lambda: True)
