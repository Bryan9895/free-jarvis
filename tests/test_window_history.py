"""Histórico de ações de janela: resultado real, limite e minimização de dados."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.router import tool_catalog
from jarvis.tools import Toolkit, TOOL_SPECS


class WindowHistoryTests(unittest.TestCase):
    def test_toolkit_records_verified_and_rejected_actions(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "state.sqlite3"
            kit = Toolkit(Path(td), approve=lambda _: True, layout_db=db)
            with patch("jarvis.window_layout.place_window", return_value={
                "status": "geometry_verified", "geometry": (10, 20, 500, 400)}):
                first = kit.execute("place_window", {"app": "firefox", "title": "Segredo",
                                                      "position": "center"})
            self.assertEqual(first["result"]["status"], "geometry_verified")
            self.assertIsInstance(first["audit_id"], int)
            with patch("jarvis.window_manage.close_window", return_value={"status": "rejected"}):
                kit.execute("close_window", {"app": "firefox", "title": "Segredo"})
            history = kit.execute("window_action_history", {"limit": 10})["result"]
            self.assertEqual([item["status"] for item in history["actions"]],
                             ["rejected", "geometry_verified"])
            self.assertEqual(history["actions"][1]["details"]["geometry"], [10, 20, 500, 400])
            self.assertNotIn("Segredo", str(history))
            kit.close()
            another = Toolkit(Path(td), layout_db=db)
            self.assertEqual(len(another.window_action_history()["actions"]), 2)
            another.close()

    def test_invalid_limit_and_router(self):
        with tempfile.TemporaryDirectory() as td:
            kit = Toolkit(Path(td), layout_db=Path(td) / "state.sqlite3")
            self.assertIn("error", kit.execute("window_action_history", {"limit": 0}))
            kit.close()
        self.assertIn("window_action_history", {item["name"] for item in TOOL_SPECS})
        selected = tool_catalog("Mostre o histórico de ações das janelas", TOOL_SPECS)
        self.assertEqual([item["name"] for item in selected], ["window_action_history"])


if __name__ == "__main__":
    unittest.main()
