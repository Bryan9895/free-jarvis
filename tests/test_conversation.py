import threading
import unittest
from unittest.mock import Mock
from jarvis.conversation import ConversationController
from jarvis.cancellation import CancelledError


class ConversationTests(unittest.TestCase):
    def test_display_and_voice_share_result_and_correlated_events(self):
        service, voice, display = Mock(), Mock(), Mock()
        service.ask.return_value = '**Abri** o [Firefox](https://example.test).'
        voice.speak.return_value = 'spoken'
        events = []
        controller = ConversationController(service, emit=events.append)
        response = controller.run('abra Firefox', voice=voice, display=display)
        service.ask.assert_called_once_with('abra Firefox')
        display.assert_called_once_with(response.display_text)
        voice.speak.assert_called_once_with('Abri o Firefox.')
        self.assertEqual(len({e.turn_id for e in events}), 1)
        self.assertEqual({e.session_id for e in events}, {controller.session_id})
        self.assertEqual([e.state for e in events], ['executando', 'falando', 'aguardando_seguimento'])
        self.assertEqual([e.at for e in events], sorted(e.at for e in events))

    def test_cancelled_late_response_never_displays_or_speaks(self):
        service, voice, display = Mock(), Mock(), Mock()
        controller = ConversationController(service)
        def late(_):
            controller.cancel()
            return 'feito'
        service.ask.side_effect = late
        with self.assertRaises(CancelledError):
            controller.run('execute', voice=voice, display=display)
        display.assert_not_called()
        voice.speak.assert_not_called()
        voice.cancel_speech.assert_called_once()
        service.ask.assert_called_once()
        service.ask.side_effect = None
        service.ask.return_value = 'novo'
        controller.run('novo', display=display)
        display.assert_called_once_with('novo')

    def test_tts_failure_keeps_display_and_does_not_replay_action(self):
        service, voice, display = Mock(), Mock(), Mock()
        service.ask.return_value = 'efeito verificado'
        voice.speak.side_effect = RuntimeError('saída ausente')
        events = []
        controller = ConversationController(service, emit=events.append)
        controller.run('execute', voice=voice, display=display)
        service.ask.assert_called_once()
        display.assert_called_once_with('efeito verificado')
        self.assertEqual(events[-1].state, 'erro')
        self.assertIn('tts:', events[-1].reason)

    def test_provider_failure_never_starts_audio_and_next_turn_can_recover(self):
        service, voice = Mock(), Mock()
        service.ask.side_effect = [RuntimeError('NIM 404'), 'recuperado']
        controller = ConversationController(service)
        with self.assertRaisesRegex(RuntimeError, '404'):
            controller.run('primeiro', voice=voice)
        voice.speak.assert_not_called()
        self.assertEqual(controller.run('segundo').display_text, 'recuperado')

    def test_parallel_turn_is_rejected(self):
        service = Mock()
        controller = ConversationController(service)
        controller._lock.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, 'turno'):
                controller.run('duplicado')
        finally:
            controller._lock.release()
        service.ask.assert_not_called()
