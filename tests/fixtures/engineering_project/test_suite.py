import json
from pathlib import Path
import sys
import unittest
from jarvis_fixture_dep import VALUE

fail = '--fail' in sys.argv
if fail:
    sys.argv.remove('--fail')


class FixtureTests(unittest.TestCase):
    def test_real_dependency(self):
        self.assertEqual(VALUE, 17)
        self.assertFalse(fail, 'Directed failure for resume evaluation')

    def test_preserved_configuration(self):
        config = json.loads(Path('config.json').read_text())
        self.assertEqual(config, {'keep': 'preserved', 'enabled': True})


result = unittest.main(exit=False).result
if not result.wasSuccessful():
    raise SystemExit(1)
print('ENGINEERING_TESTS_OK')
