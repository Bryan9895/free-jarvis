"""Argumentos do modelo são verificados antes do executor e da aprovação."""
import tempfile
import unittest
from pathlib import Path

from jarvis.tools import Toolkit


class SchemaValidationTests(unittest.TestCase):
    def test_invalid_types_and_unknown_fields_never_reach_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            approvals = []
            kit = Toolkit(Path(temp), approve=lambda action: approvals.append(action) or True)
            for arguments in (
                {"path": "a.txt", "content": 123},
                {"path": "a.txt", "content": "x", "extra": "surpresa"},
                {"content": "x"},
            ):
                with self.subTest(arguments=arguments):
                    self.assertIn("error", kit.execute("write_file", arguments))
            self.assertFalse(approvals)
            self.assertFalse((Path(temp) / "a.txt").exists())
            kit.close()

    def test_nested_window_schema_rejects_invalid_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            kit = Toolkit(Path(temp), approve=lambda _: self.fail("executor chamado"))
            outcome = kit.execute("arrange_window_grid", {"windows": [
                {"app": "Firefox"}, {"app": "Code"}, {"app": "Terminal", "title": 3}]})
            self.assertIn("Tipo inválido", outcome["error"])
            self.assertIn("error", kit.execute("arrange_window_grid", {"windows": [
                {"app": "Firefox"}, {"app": "Code"}]}))
            kit.close()

    def test_bool_is_not_integer_and_excessively_large_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            kit = Toolkit(Path(temp))
            self.assertIn("error", kit.execute("activate_workspace",
                                               {"workspace_number": True}))
            self.assertIn("256 KB", kit.execute("write_file",
                                              {"path": "x", "content": "z" * 260_000})["error"])
            kit.close()


if __name__ == "__main__":
    unittest.main()
