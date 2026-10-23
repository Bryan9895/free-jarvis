import unittest
from unittest.mock import Mock
from jarvis.audio_devices import input_format


class InputFormatTests(unittest.TestCase):
    def test_preferred_mono_when_supported(self):
        backend = Mock()
        backend.query_devices.return_value = {'name': 'mic', 'default_samplerate': 48000, 'max_input_channels': 2}
        result = input_format(backend, 'mic')
        self.assertEqual((result.rate, result.channels), (16000, 1))
        backend.check_input_settings.assert_called_once()

    def test_native_stereo_is_negotiated_without_changing_system_default(self):
        backend = Mock()
        backend.query_devices.return_value = {'name': 'Bluetooth', 'default_samplerate': 48000, 'max_input_channels': 2}
        backend.check_input_settings.side_effect = [ValueError('taxa'), ValueError('mono'), None]
        result = input_format(backend, 'Bluetooth')
        self.assertEqual((result.rate, result.channels), (48000, 2))
        self.assertEqual(backend.method_calls[0].args, ('Bluetooth',))
        self.assertEqual(len(backend.method_calls), 4)

    def test_unsupported_format_fails_explicitly(self):
        backend = Mock()
        backend.query_devices.return_value = {'name': 'mic', 'default_samplerate': 48000, 'max_input_channels': 1}
        backend.check_input_settings.side_effect = RuntimeError('desconectado')
        with self.assertRaisesRegex(RuntimeError, 'PCM16'):
            input_format(backend, 'mic')
