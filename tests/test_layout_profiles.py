"""Perfis de janelas: persistência e restauração sem controlar GNOME no CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.layout_profiles import (save_window_layout, list_window_layouts,
                                    restore_window_layout)
from jarvis.router import tool_catalog
from jarvis.tools import TOOL_SPECS, Toolkit


def window(ident, app, title, x, width):
    return {"id": ident, "app": app, "title": title, "pid": ident + 10,
            "monitor": 0, "x": x, "y": 0, "width": width, "height": 800,
            "is_minimized": False, "is_maximized": False}


class LayoutProfileTests(unittest.TestCase):
    def test_save_list_and_restore_scales_to_new_workarea(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "memory.sqlite3"
            old = [window(1, "code", "Editor", 0, 500),
                   window(2, "firefox", "Docs", 500, 500)]
            selectors = [{"app": "code"}, {"app": "firefox"}]
            with patch("jarvis.layout_profiles._inventory", return_value=old), patch(
                "jarvis.layout_profiles._workarea", return_value=(0, 0, 1000, 800)):
                saved = save_window_layout(db, "programação", selectors, lambda _: True)
            self.assertEqual(saved["status"], "saved")
            self.assertEqual(list_window_layouts(db)["profiles"][0]["name"], "programação")
            with patch("jarvis.layout_profiles._inventory", return_value=old), patch(
                "jarvis.layout_profiles._workarea", return_value=(100, 20, 2000, 1600)), patch(
                "jarvis.layout_profiles._place_one", return_value=True) as place, patch(
                "jarvis.layout_profiles._placement_verified", return_value=True):
                result = restore_window_layout(db, "programação", lambda _: True)
            self.assertEqual(result["status"], "layout_verified")
            self.assertEqual(place.call_args_list[0].args[1], (100, 20, 1000, 1600))
            self.assertEqual(place.call_args_list[1].args[1], (1100, 20, 1000, 1600))

    def test_save_rejects_ambiguous_and_changed_windows(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "db.sqlite3"
            before = [window(1, "firefox", "A", 0, 500),
                      window(2, "firefox", "B", 500, 500)]
            with patch("jarvis.layout_profiles._inventory", return_value=before), patch(
                "jarvis.layout_profiles._workarea", return_value=(0, 0, 1000, 800)):
                result = save_window_layout(db, "web", [{"app": "firefox"},
                                                        {"app": "firefox"}], lambda _: True)
            self.assertEqual(result["status"], "ambiguous")
            changed = [before[0], {**before[1], "x": 400}]
            with patch("jarvis.layout_profiles._inventory", side_effect=[before, changed]), patch(
                "jarvis.layout_profiles._workarea", return_value=(0, 0, 1000, 800)):
                result = save_window_layout(db, "web", [{"app": "firefox", "title": "A"},
                                                        {"app": "firefox", "title": "B"}],
                                            lambda _: True)
            self.assertEqual(result["status"], "changed")
            self.assertEqual(list_window_layouts(db)["profiles"], [])

    def test_restore_does_not_move_when_identity_changes(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "db.sqlite3"
            old = [window(1, "code", "Editor", 0, 500),
                   window(2, "firefox", "Docs", 500, 500)]
            with patch("jarvis.layout_profiles._inventory", return_value=old), patch(
                "jarvis.layout_profiles._workarea", return_value=(0, 0, 1000, 800)):
                save_window_layout(db, "work", [{"app": "code"}, {"app": "firefox"}],
                                   lambda _: True)
            changed = [old[0], {**old[1], "id": 9}]
            with patch("jarvis.layout_profiles._inventory", side_effect=[old, changed]), patch(
                "jarvis.layout_profiles._workarea", return_value=(0, 0, 1000, 800)), patch(
                "jarvis.layout_profiles._place_one") as place:
                result = restore_window_layout(db, "work", lambda _: True)
            self.assertEqual(result["status"], "changed")
            place.assert_not_called()

    def test_toolkit_and_router_expose_profile_tools(self):
        names = {spec["name"] for spec in TOOL_SPECS}
        self.assertTrue({"save_window_layout", "restore_window_layout",
                         "list_window_layouts"} <= names)
        self.assertEqual([spec["name"] for spec in tool_catalog(
            "Restaure o perfil programação", TOOL_SPECS)], ["restore_window_layout"])
        with tempfile.TemporaryDirectory() as td:
            kit = Toolkit(Path(td), layout_db=Path(td) / "db.sqlite3")
            self.assertEqual(kit.execute("list_window_layouts", {})["result"]["status"],
                             "listed")
            kit.close()


if __name__ == "__main__":
    unittest.main()
