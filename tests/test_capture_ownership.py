import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase, skipUnless

from jarvis.capture import CaptureLock
from jarvis.capture import FrameBus, FrameLossError


@skipUnless(os.name == 'posix', 'Linux file ownership')
class CaptureOwnershipTests(TestCase):
    def test_bounded_shared_frames_are_immutable_and_loss_is_explicit(self):
        import numpy as np
        bus = FrameBus()
        with bus.subscribe(1) as wake, bus.subscribe(1) as vad:
            bus.publish(np.array([1, 2], dtype=np.int16))
            first, second = wake.receive(), vad.receive()
            self.assertIs(first, second)
            with self.assertRaises(ValueError): first[0] = 3
            bus.publish(first)
            bus.publish(first)
            with self.assertRaises(FrameLossError): wake.receive()
            self.assertEqual(vad.lost, 1)
    def test_another_process_cannot_capture_until_owner_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'capture.lock'
            lock = CaptureLock(path)
            script = ('from jarvis.capture import CaptureLock; import sys; '
                      'lock=CaptureLock(sys.argv[1]); acquired=lock.acquire(False); '
                      'print(acquired); lock.release() if acquired else None')
            with lock:
                blocked = subprocess.check_output([sys.executable, '-c', script, str(path)], text=True)
            free = subprocess.check_output([sys.executable, '-c', script, str(path)], text=True)
            self.assertEqual(blocked.strip(), 'False')
            self.assertEqual(free.strip(), 'True')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
