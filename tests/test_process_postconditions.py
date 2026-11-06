import hashlib
from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

from jarvis.approval import ApprovalPolicy
from jarvis.tools import Toolkit


class ProcessPostconditionTests(TestCase):
    def test_zero_exit_needs_explicit_matching_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            toolkit = Toolkit(Path(directory), approve=ApprovalPolicy(manual_callback=lambda _: True))
            command = [sys.executable, '-c', 'print("verified output")']
            plain = toolkit.execute_process(command)
            self.assertFalse(plain['effect_verified'])
            checks = {'stdout_sha256': hashlib.sha256(b'verified output\n').hexdigest()}
            passed = toolkit.execute_process(command, postconditions=checks)
            self.assertEqual(passed['status'], 'verified')
            mismatch = toolkit.execute_process(command, postconditions={'stdout_sha256': '0' * 64})
            self.assertEqual(mismatch['status'], 'failed')
            nonzero = toolkit.execute_process([sys.executable, '-c', 'print("verified output");exit(1)'], postconditions=checks)
            self.assertEqual(nonzero['status'], 'failed')

    def test_invalid_or_unauthorized_checks_fail_before_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            toolkit = Toolkit(Path(directory), approve=ApprovalPolicy(manual_callback=lambda _: True))
            for checks in ({}, {'revision': 12}, {'distributions': ['package']},
                           {'files': [{'path': '/etc/passwd', 'sha256': '0' * 64}]}):
                with self.subTest(checks=checks), patch('jarvis.command_execution.limited_process') as run:
                    with self.assertRaises(ValueError): toolkit.execute_process(['/bin/true'], postconditions=checks)
                    run.assert_not_called()
