import os
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jarvis.audio_output import play_pipeline, LiveSpeech
from jarvis.cancellation import CancelledError
from jarvis.speech_text import SentenceBuffer, speech_chunks


class AudioOutputTests(unittest.TestCase):
    def test_next_sentence_is_synthesized_during_playback_and_files_removed(self):
        second = Event()
        paths = []
        played = []
        def synthesize(_model, text, path, _cancel):
            paths.append(path)
            path.write_text(text)
            if text == 'segunda': second.set()
        def play(args):
            path = Path(args[-1])
            played.append(path.read_text())
            if len(played) == 1:
                self.assertTrue(second.wait(1))
        voice = SimpleNamespace(piper_model='model', _speech_cancel=Event(), output_device='', _run_audio=play)
        with patch('jarvis.tts_engine.synthesizer.synthesize', side_effect=synthesize):
            self.assertEqual(play_pipeline(voice, iter(('primeira', 'segunda', 'terceira'))), 'spoken')
        self.assertEqual(played, ['primeira', 'segunda', 'terceira'])
        self.assertTrue(all(not path.exists() for path in paths))

    def test_playback_failure_cleans_queued_audio(self):
        paths = []
        def synthesize(_model, text, path, _cancel):
            paths.append(path)
            path.write_text(text)
        def fail(_): raise RuntimeError('player failed')
        voice = SimpleNamespace(piper_model='model', _speech_cancel=Event(), output_device='', _run_audio=fail)
        with patch('jarvis.tts_engine.synthesizer.synthesize', side_effect=synthesize):
            with self.assertRaisesRegex(RuntimeError, 'player failed'):
                play_pipeline(voice, iter(str(i) for i in range(100)))
        self.assertTrue(all(not path.exists() for path in paths))

    def test_live_first_sentence_precedes_provider_final_without_repetition(self):
        spoken, first = [], Event()
        class Voice:
            _speech_cancel = Event()
            def speak_stream(self, chunks):
                for chunk in chunks:
                    spoken.append(chunk)
                    first.set()
                return 'spoken'
            def cancel_speech(self): self._speech_cancel.set()
        live = LiveSpeech(Voice())
        live.feed('Primeira frase. ')
        self.assertTrue(first.wait(1))
        live.feed('Segunda frase.')
        self.assertEqual(live.finish('Primeira frase. Segunda frase.'), 'spoken')
        self.assertEqual(spoken, ['Primeira frase.', 'Segunda frase.'])

    def test_no_delta_still_speaks_all_final_text_once(self):
        spoken = []
        class Voice:
            _speech_cancel = Event()
            def speak_stream(self, chunks):
                spoken.extend(chunks)
                return 'spoken'
            def cancel_speech(self): self._speech_cancel.set()
        live = LiveSpeech(Voice())
        live.finish('Uma frase. Outra frase.')
        self.assertEqual(spoken, ['Uma frase.', 'Outra frase.'])

    def test_sentence_buffer_preserves_abbreviations_numbers_and_code(self):
        buffer = SentenceBuffer()
        self.assertEqual(buffer.feed('Dr. Silva pagou 3.14 reais. Ainda'), ['Dr. Silva pagou 3.14 reais.'])
        self.assertEqual(buffer.feed(' falta.'), [])
        self.assertEqual(buffer.finish(), ['Ainda falta.'])
        chunks = list(speech_chunks('Veja ```python\nprint("x. y")\n``` e prossiga.'))
        self.assertIn('print("x. y")', ' '.join(chunks))
