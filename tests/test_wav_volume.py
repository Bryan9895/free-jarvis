import os
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from threading import Event

from jarvis.wav_volume import attenuate_wav
from jarvis.cancellation import CancelledError


class VolumeTests(unittest.TestCase):
    def test_gain_is_applied_to_pcm_only(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'voice.wav'
            def create(samples):
                with wave.open(str(source), 'wb') as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(16000)
                    stream.writeframes(array('h', samples).tobytes())
            def read():
                with wave.open(str(source), 'rb') as stream:
                    return list(array('h', stream.readframes(stream.getnframes())))
            create([-32000, -1000, 0, 1000, 32000])
            attenuate_wav(source, .5)
            self.assertEqual(read(), [-16000, -500, 0, 500, 16000])
            attenuate_wav(source, 0)
            self.assertEqual(read(), [0] * 5)
            self.assertEqual(list(Path(folder).iterdir()), [source])

    def test_full_volume_is_noop_and_bad_values_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'wave.wav'
            path.write_bytes(b'not a real WAV')
            attenuate_wav(path, 1)
            self.assertEqual(path.read_bytes(), b'not a real WAV')
            for gain in (-1, 1.1, None):
                with self.assertRaises(ValueError):
                    attenuate_wav(path, gain)

    def test_cancel_does_not_replace_original_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'voice.wav'
            with wave.open(str(source), 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(array('h', [1000] * 20000).tobytes())
            before = source.read_bytes()
            cancel = Event()
            cancel.set()
            with self.assertRaises(CancelledError):
                attenuate_wav(source, .3, cancel)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(list(Path(folder).iterdir()), [source])
