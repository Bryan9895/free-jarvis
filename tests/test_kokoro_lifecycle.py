import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from threading import Event, Timer
from time import monotonic
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch
import wave

from jarvis.cancellation import CancelledError
from jarvis.kokoro_engine import KokoroSynthesizer

if sys.platform == 'linux':
    import fcntl


@skipUnless(sys.platform == 'linux', 'Linux worker lifecycle')
class KokoroLifecycleTests(TestCase):
    def assets(self, root):
        from jarvis.kokoro_assets import FILES
        for name in (*FILES, 'SOURCE.json'):
            (root / name).write_bytes(b'fixture')

    def spawner(self, code, children, *, small_pipe=False):
        original = subprocess.Popen
        def start(command, **kwargs):
            self.assertTrue(kwargs['start_new_session'])
            process = original([sys.executable, '-I', '-c', code], **kwargs)
            if small_pipe: fcntl.fcntl(process.stdin, fcntl.F_SETPIPE_SZ, 4096)
            children.append(process)
            return process
        return start

    def test_cancel_and_timeout_cover_a_worker_that_never_reads_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assets(root)
            for cancelled in (True, False):
                with self.subTest(cancelled=cancelled):
                    engine, children, cancel = KokoroSynthesizer(), [], Event()
                    target = root / 'result.wav'
                    target.write_bytes(b'original')
                    timer = Timer(.15, cancel.set) if cancelled else None
                    if timer: timer.start()
                    started = monotonic()
                    try:
                        with patch('jarvis.kokoro_engine.subprocess.Popen', side_effect=self.spawner(
                                'import time;time.sleep(30)', children, small_pipe=True)):
                            with self.assertRaises(CancelledError if cancelled else TimeoutError):
                                engine.synthesize(root, 'x' * 65536, target, cancel,
                                    python=sys.executable, timeout=2 if cancelled else .15)
                        self.assertLess(monotonic() - started, 2)
                        self.assertEqual(target.read_bytes(), b'original')
                        self.assertFalse(list(root.glob('.jarvis-kokoro-*')))
                        self.assertTrue(all(child.poll() is not None for child in children))
                    finally:
                        if timer: timer.join()
                        engine.close()

    def test_cancel_while_waiting_does_not_close_another_request_worker(self):
        engine, cancel, owner = KokoroSynthesizer(), Event(), Mock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assets(root)
            engine._process = owner
            timer = Timer(.1, cancel.set)
            engine._lock.acquire()
            timer.start()
            try:
                with self.assertRaises(CancelledError):
                    engine.synthesize(root, 'frase', root / 'out.wav', cancel, python=sys.executable)
                self.assertIs(engine._process, owner)
                owner.terminate.assert_not_called()
            finally:
                timer.join()
                engine._process = None
                engine._lock.release()

    def test_timeout_reaps_descendant_that_ignores_sigterm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assets(root)
            marker = root / 'child.pid'
            child_code = ('import signal,time,os;from pathlib import Path;'
                          'signal.signal(signal.SIGTERM,signal.SIG_IGN);'
                          f'Path({str(marker)!r}).write_text(str(os.getpid()));time.sleep(30)')
            worker = ('import subprocess,sys,time;'
                      f'subprocess.Popen([sys.executable,"-c",{child_code!r}]);'
                      'sys.stdin.readline();time.sleep(30)')
            engine, children = KokoroSynthesizer(), []
            try:
                with patch('jarvis.kokoro_engine.subprocess.Popen', side_effect=self.spawner(worker, children)):
                    with self.assertRaises(TimeoutError):
                        engine.synthesize(root, 'frase', root / 'out.wav', Event(), python=sys.executable, timeout=.5)
                self.assertTrue(marker.is_file())
                pid = int(marker.read_text())
                deadline = monotonic() + 1
                while monotonic() < deadline:
                    stat = Path(f'/proc/{pid}/stat')
                    if not stat.exists() or stat.read_text().rsplit(')', 1)[1].split()[0] == 'Z': break
                    Event().wait(.02)
                else: self.fail('Owned descendant remained alive')
                self.assertTrue(all(child.poll() is not None for child in children))
            finally:
                engine.close()
                for child in children:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass

    def test_truncated_wav_never_replaces_existing_target(self):
        code = '''import json,sys,wave,struct
for line in sys.stdin:
 request=json.loads(line)
 with wave.open(request['filename'],'wb') as wav:
  wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(b'\\0\\0'*240)
 with open(request['filename'],'r+b') as wav:
  wav.seek(40);wav.write(struct.pack('<I',4800))
 print('{"ok":true}',flush=True)
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assets(root)
            target = root / 'out.wav'
            target.write_bytes(b'original')
            engine, children = KokoroSynthesizer(), []
            try:
                with patch('jarvis.kokoro_engine.subprocess.Popen', side_effect=self.spawner(code, children)):
                    with self.assertRaisesRegex(ValueError, 'truncado'):
                        engine.synthesize(root, 'frase', target, Event(), python=sys.executable)
                self.assertEqual(target.read_bytes(), b'original')
                self.assertFalse(list(root.glob('.jarvis-kokoro-*')))
            finally:
                engine.close()

    def test_invalid_request_is_rejected_before_spawn(self):
        engine = KokoroSynthesizer()
        with patch('jarvis.kokoro_engine.subprocess.Popen') as spawn:
            for text, timeout in (('', 1), ('x' * 65537, 1), ('frase', float('nan'))):
                with self.assertRaises(ValueError):
                    engine.synthesize('/not/read', text, '/not/written', Event(), python=sys.executable, timeout=timeout)
        spawn.assert_not_called()
