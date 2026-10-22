"""Perfis de ambiente com compositor simulado; sem alterar o desktop CI."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.agent import _local_layout_reply
from jarvis.desktop_profiles import (save_desktop_profile, list_desktop_profiles,
                                     restore_desktop_profile)
from jarvis.router import tool_catalog
from jarvis.tools import TOOL_SPECS, Toolkit


MONITORS = [{"index": 0, "x": 0, "y": 0, "width": 1200, "height": 800,
             "scale": 1, "connector": "eDP-1", "is_primary": True}]
SPACES = [{"index": 0, "name": "Trabalho", "is_active": True, "window_count": 2},
          {"index": 1, "name": "Estudos", "is_active": False, "window_count": 0}]
AREA = (0, 0, 1200, 800)


def window(ident, app, title, x, *, workspace=0, width=500):
    return {"id": ident, "app": app, "title": title, "pid": ident + 100,
            "monitor": 0, "workspace_index": workspace,
            "x": x, "y": 100, "width": width, "height": 500,
            "is_minimized": False, "is_maximized": False}


class DesktopProfileTests(unittest.TestCase):
    def _save(self, db, selectors, rows):
        with patch("jarvis.desktop_profiles._inventory", return_value=rows), patch(
            "jarvis.desktop_profiles._monitors", return_value=MONITORS), patch(
            "jarvis.desktop_profiles._workspaces", return_value=SPACES), patch(
            "jarvis.desktop_profiles._workarea", return_value=AREA):
            return save_desktop_profile(db, "programacao", selectors, lambda _: True)

    def test_save_and_list_persist_real_window_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/"jarvis.db"
            rows = [window(1, "code", "Editor", 0),
                    window(2, "firefox", "Docs", 600)]
            selectors = [{"app": "code", "title": "Editor", "app_id": "code"},
                         {"app": "firefox", "title": "Docs", "app_id": "firefox"}]
            self.assertEqual(self._save(db, selectors, rows)["status"], "saved")
            self.assertEqual(list_desktop_profiles(db)["profiles"][0]["name"],
                             "programacao")
            connection = sqlite3.connect(db)
            try:
                payload = connection.execute(
                    "SELECT payload FROM desktop_profiles WHERE name='programacao'").fetchone()[0]
            finally:
                connection.close()
            self.assertIn('"workspace_index": 0', payload)
            self.assertIn('"connector": "eDP-1"', payload)

    def test_restore_moves_existing_window_then_verifies_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/"jarvis.db"
            original = window(1, "code", "Editor", 0)
            self.assertEqual(self._save(db, [{"app": "code", "title": "Editor"}],
                                        [original])["status"], "saved")
            state = {"window": window(1, "code", "Editor", 300, workspace=1)}
            def inventory():
                return [dict(state["window"])]
            def move(app, number, approve, title):
                state["window"]["workspace_index"] = number - 1
                return {"status": "window_workspace_verified"}
            def place(app, position, approve, **kwargs):
                state["window"].update(x=kwargs["x_px"], y=kwargs["y_px"],
                                       width=kwargs["width_px"],
                                       height=kwargs["height_px"])
                return {"status": "geometry_verified"}
            with patch("jarvis.desktop_profiles._inventory", side_effect=inventory), patch(
                "jarvis.desktop_profiles._monitors", return_value=MONITORS), patch(
                "jarvis.desktop_profiles._workspaces", return_value=SPACES), patch(
                "jarvis.desktop_profiles._workarea", return_value=AREA), patch(
                "jarvis.desktop_profiles.move_window_to_workspace", side_effect=move) as mover, patch(
                "jarvis.desktop_profiles.place_window", side_effect=place) as placer:
                result = restore_desktop_profile(db, "programacao", lambda _: True)
            self.assertEqual(result["status"], "profile_verified")
            self.assertEqual([step["status"] for step in result["outcomes"][0]["steps"]],
                             ["window_workspace_verified", "geometry_verified",
                              "state_verified"])
            mover.assert_called_once()
            placer.assert_called_once()

    def test_launch_uncertain_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/"jarvis.db"
            self._save(db, [{"app": "code", "title": "Editor", "app_id": "code"}],
                       [window(1, "code", "Editor", 0)])
            with patch("jarvis.desktop_profiles._inventory", return_value=[]), patch(
                "jarvis.desktop_profiles._monitors", return_value=MONITORS), patch(
                "jarvis.desktop_profiles._workspaces", return_value=SPACES), patch(
                "jarvis.desktop_profiles._workarea", return_value=AREA), patch(
                "jarvis.desktop_profiles.launch_installed_app",
                return_value={"status": "launched_unverified"}) as launch, patch(
                "jarvis.desktop_profiles._wait_window",
                return_value=(None, "not_observed")):
                first = restore_desktop_profile(db, "programacao", lambda _: True)
                second = restore_desktop_profile(db, "programacao", lambda _: True)
            self.assertEqual(first["status"], "profile_partial")
            self.assertEqual(second["status"], "launch_uncertain")
            launch.assert_called_once()

    def test_observed_launch_is_reused_on_next_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/"jarvis.db"
            editor = window(1, "code", "Editor", 0)
            self._save(db, [{"app": "code", "title": "Editor", "app_id": "code"}],
                       [editor])
            state = {"rows": []}
            def launch(*_args):
                state["rows"] = [editor]
                return {"status": "launched_unverified"}
            with patch("jarvis.desktop_profiles._inventory",
                       side_effect=lambda: list(state["rows"])), patch(
                "jarvis.desktop_profiles._monitors", return_value=MONITORS), patch(
                "jarvis.desktop_profiles._workspaces", return_value=SPACES), patch(
                "jarvis.desktop_profiles._workarea", return_value=AREA), patch(
                "jarvis.desktop_profiles.launch_installed_app",
                side_effect=launch) as launcher:
                first = restore_desktop_profile(db, "programacao", lambda _: True)
                second = restore_desktop_profile(db, "programacao", lambda _: True)
            self.assertEqual(first["status"], "profile_verified")
            self.assertEqual(second["status"], "profile_verified")
            launcher.assert_called_once()

    def test_preflight_blocks_ambiguous_and_missing_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/"jarvis.db"
            self._save(db, [{"app": "code", "title": "Editor"}],
                       [window(1, "code", "Editor", 0)])
            with patch("jarvis.desktop_profiles._inventory", return_value=[]), patch(
                "jarvis.desktop_profiles._monitors", return_value=MONITORS), patch(
                "jarvis.desktop_profiles._workspaces", return_value=SPACES), patch(
                "jarvis.desktop_profiles._workarea", return_value=AREA), patch(
                "jarvis.desktop_profiles.launch_installed_app") as launch:
                self.assertEqual(restore_desktop_profile(
                    db, "programacao", lambda _: True)["status"], "not_observed")
                launch.assert_not_called()
            with patch("jarvis.desktop_profiles._inventory", return_value=[
                    window(1, "code", "Editor", 0),
                    window(2, "code", "Editor Extra", 600)]), patch(
                "jarvis.desktop_profiles._monitors", return_value=MONITORS), patch(
                "jarvis.desktop_profiles._workspaces", return_value=SPACES), patch(
                "jarvis.desktop_profiles._workarea", return_value=AREA):
                self.assertEqual(restore_desktop_profile(
                    db, "programacao", lambda _: True)["status"], "ambiguous")

    def test_invalid_saved_payload_and_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/"jarvis.db"
            self._save(db, [{"app": "code", "title": "Editor"}],
                       [window(1, "code", "Editor", 0)])
            connection = sqlite3.connect(db)
            try:
                connection.execute("UPDATE desktop_profiles SET payload='{}'")
                connection.commit()
            finally:
                connection.close()
            with self.assertRaises(ValueError):
                restore_desktop_profile(db, "programacao", lambda _: True)
        for prompt, expected in [
            ("Jarvis, salve meu ambiente de programação", "save_desktop_profile"),
            ("Jarvis, liste meus ambientes", "list_desktop_profiles"),
            ("Jarvis, abra meu ambiente de programação", "restore_desktop_profile")]:
            with self.subTest(prompt=prompt):
                self.assertEqual([item["name"] for item in tool_catalog(prompt, TOOL_SPECS)],
                                 [expected])

    def test_toolkit_audit_and_local_reply(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
                "jarvis.desktop_profiles.restore_desktop_profile",
                return_value={"status": "profile_verified", "name": "programacao",
                              "outcomes": [{"app": "code", "title": "Secret",
                                            "steps": [{"action": "verify",
                                                       "status": "state_verified"}]}]}):
            kit = Toolkit(Path(tmp)/"workspace", approve=lambda _: True,
                          layout_db=Path(tmp)/"jarvis.db")
            result = kit.execute("restore_desktop_profile", {"name": "programacao"})
            history = kit.execute("window_action_history", {"limit": 1})
        self.assertEqual(result["audit_id"], 1)
        self.assertEqual(history["result"]["actions"][0]["details"],
                         {"name": "programacao", "steps": [
                             {"action": "verify", "status": "state_verified"}]})
        self.assertIn("verificado", _local_layout_reply(
            [{"name": "restore_desktop_profile"}], [result]))


if __name__ == "__main__":
    unittest.main()
