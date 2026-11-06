import json
from pathlib import Path
import tempfile
from unittest import TestCase, skipUnless

from tools.validate_engineering import Fixture, make_service, prepare, report


@skipUnless(__import__('sys').platform == 'linux', 'Linux project service fixture')
class EngineeringJourneyTests(TestCase):
    def test_failed_test_then_restart_resumes_without_clone_or_install_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory) / 'journey', create=True)
            service = make_service(fixture, fail_tests=True)
            try:
                prepare(service, fixture)
                service.plan_action('execute')
                first = service.planner.snapshot()
                self.assertEqual(first['status'], 'stopped', json.dumps(first))
                self.assertEqual([step['status'] for step in first['steps']],
                                 ['verified', 'verified', 'verified', 'blocked', 'pending'])
                self.assertFalse((fixture.root / 'source/.venv').exists())
                before = (fixture.project / '.venv/pyvenv.cfg').read_bytes()
                service.close()
                service = make_service(fixture)
                service.planner.resolve_step('retry')
                service.planner.ready_to_resume()
                service.plan_action('execute')
                result = report(service, fixture)
                self.assertEqual(result['plan_state'], 'completed_verified', json.dumps(service.planner.snapshot()))
                self.assertTrue(result['health_verified'])
                self.assertTrue(result['revision_matches'])
                self.assertTrue(result['configuration_preserved'])
                self.assertEqual(result['install_count'], 1)
                self.assertEqual((fixture.project / '.venv/pyvenv.cfg').read_bytes(), before)
                self.assertEqual(service.client.tool_requests, ['execute_process', 'project_service'])
                identity = result['service_identity']
                arguments = fixture.commands()[-1][1]
                repeated = service.toolkit.project_service(**arguments)
                self.assertTrue(repeated['reused'])
                self.assertEqual(repeated['identity'], identity)
            finally:
                if fixture.project.exists():
                    service.toolkit.project_service('stop', 'engineering-fixture', str(fixture.project))
                service.close()

    def test_modified_configuration_blocks_resume_before_next_command(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory) / 'journey', create=True)
            service = make_service(fixture, fail_tests=True)
            try:
                prepare(service, fixture)
                service.plan_action('execute')
                count = len(service.client.tool_requests)
                (fixture.project / 'config.json').write_text('{"keep":"changed","enabled":true}\n')
                service.planner.resolve_step('retry')
                service.planner.ready_to_resume()
                service.plan_action('execute')
                self.assertEqual(service.planner.snapshot()['status'], 'stopped')
                self.assertEqual(len(service.client.tool_requests), count)
                self.assertEqual((fixture.project / 'install-count.txt').read_text(), '1\n')
            finally:
                service.close()
