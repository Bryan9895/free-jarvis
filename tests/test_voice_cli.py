"""Audio discovery must work without FCC initialization."""
import sys
import unittest
from unittest.mock import patch
from jarvis.cli import main
from jarvis.voice import VoiceError

class VoiceCliTests(unittest.TestCase):
    def test_devices_does_not_construct_fcc_client(self):
        with patch.object(sys, "argv", ["jarvis-fcc", "--audio-devices"]), patch(
                "jarvis.voice.VoiceIO.input_devices", return_value=[(5, "Bluetooth")]), patch(
                "jarvis.cli.FCCClient") as client, patch("builtins.print") as output:
            main()
        client.assert_not_called()
        output.assert_called_once_with("5: Bluetooth")

    def test_device_discovery_failure_exits_cleanly(self):
        with patch.object(sys, "argv", ["jarvis-fcc", "--audio-devices"]), patch(
                "jarvis.voice.VoiceIO.input_devices", side_effect=VoiceError("indisponível")):
            with self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code, 1)
