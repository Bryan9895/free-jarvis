import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
from unittest import TestCase, skipUnless
from unittest.mock import patch

from jarvis.project_services import ProjectServices, health_url
from jarvis.tools import Toolkit
from jarvis.approval import ApprovalPolicy


@skipUnless(sys.platform == 'linux', 'Linux process identity')
class ProjectServicesTests(TestCase):
    def test_resume_reuses_live_service_and_stop_revalidates_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', 0))
                port = reservation.getsockname()[1]
            argv = [sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1']
            health = f'http://127.0.0.1:{port}/'
            original = ProjectServices(root / 'state.sqlite')
            resumed = ProjectServices(root / 'state.sqlite')
            try:
                first = original.operate('start', 'fixture', root, argv=argv, health=health)
                self.assertEqual(first['status'], 'verified')
                with patch('jarvis.project_services.subprocess.Popen', side_effect=AssertionError('Duplicate effect')):
                    again = resumed.operate('start', 'fixture', root, argv=argv, health=health)
                self.assertTrue(again['reused'])
                self.assertEqual(first['identity'], again['identity'])
                self.assertEqual(resumed.operate('status', 'fixture', root)['status'], 'verified')
                with patch('jarvis.project_services.identity', return_value={'pid': first['identity']['pid'], 'starttime': 'foreign'}), \
                        patch('jarvis.project_services.os.killpg') as kill:
                    rejected = resumed.operate('stop', 'fixture', root)
                self.assertFalse(rejected['effect_verified'])
                kill.assert_not_called()
                stopped = resumed.operate('stop', 'fixture', root)
                self.assertTrue(stopped['stopped'])
                self.assertEqual(resumed.operate('status', 'fixture', root)['status'], 'not_running')
            finally:
                for child in original.children.values():
                    if child.poll() is None:
                        os.killpg(child.pid, 9)
                    child.wait()

    def test_uncertain_start_is_not_retried_and_no_arbitrary_execution_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = ProjectServices(root / 'state.sqlite')
            manager.operate('status', 'fixture', root)
            with sqlite3.connect(manager.database) as conn:
                conn.execute('INSERT INTO project_services VALUES (?,?,?)',
                             (str(root), 'fixture', '{"state":"starting","identity":null}'))
            with patch('jarvis.project_services.subprocess.Popen') as spawn:
                result = manager.operate('start', 'fixture', root, argv=['/bin/true'], health='http://127.0.0.1:9999/health')
            self.assertFalse(result['effect_verified'])
            spawn.assert_not_called()
            toolkit = Toolkit(root, approve=ApprovalPolicy(), offline=True)
            self.assertIn('error', toolkit.execute('project_service', {'action': 'start', 'name': 'fixture'}))

    def test_health_is_loopback_only_and_start_requires_terminal_grant(self):
        for url in ('http://example.org/health', 'http://user:secret@127.0.0.1:8080/', 'http://127.0.0.1:8080/?token=x'):
            with self.assertRaises(ValueError): health_url(url)
        with tempfile.TemporaryDirectory() as directory:
            toolkit = Toolkit(Path(directory), approve=ApprovalPolicy())
            self.assertEqual(toolkit.project_service('start', 'fixture')['status'], 'rejected')
