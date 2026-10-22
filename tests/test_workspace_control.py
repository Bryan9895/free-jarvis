"""Movimento de áreas GNOME com respostas simuladas; sem mexer no desktop CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.agent import _local_layout_reply
from jarvis.router import tool_catalog
from jarvis.tools import TOOL_SPECS, Toolkit
from jarvis.workspace_control import activate_workspace, move_window_to_workspace


def spaces(active=0):
    return [{"index": index, "name": str(index), "is_active": index == active,
             "window_count": 1} for index in (0, 1)]


def window(index=0, ident=17):
    return {"id": ident, "app": "XTerm", "title": "Disposable", "pid": 1234,
            "workspace_index": index, "is_on_all_workspaces": False}


class WorkspaceControlTests(unittest.TestCase):
    def test_activate_revalidates_and_observes_active_area(self):
        with patch("jarvis.workspace_control._workspaces",
                   side_effect=[spaces(), spaces(), spaces(1)]), patch(
            "jarvis.workspace_control._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")) as dbus:
            result = activate_workspace(2, lambda _: True)
        self.assertEqual(result["status"], "workspace_verified")
        dbus.assert_called_once_with("ActivateWorkspace", 1)

    def test_activate_refuses_missing_changed_and_denied(self):
        with patch("jarvis.workspace_control._workspaces", return_value=spaces()):
            self.assertEqual(activate_workspace(3, lambda _: True)["status"], "not_found")
            self.assertEqual(activate_workspace(1, lambda _: True)["status"],
                             "already_in_state")
            with self.assertRaises(ValueError):
                activate_workspace(True, lambda _: True)
        with patch("jarvis.workspace_control._workspaces", return_value=spaces()), patch(
                "jarvis.workspace_control._dbus") as dbus:
            self.assertEqual(activate_workspace(2, lambda _: False)["status"], "rejected")
            dbus.assert_not_called()
        with patch("jarvis.workspace_control._workspaces",
                   side_effect=[spaces(), spaces(1)]), patch(
            "jarvis.workspace_control._dbus") as dbus:
            self.assertEqual(activate_workspace(2, lambda _: True)["status"], "changed")
            dbus.assert_not_called()

    def test_move_revalidates_identity_and_observes_workspace(self):
        before, after = window(), window(1)
        with patch("jarvis.workspace_control._workspaces",
                   side_effect=[spaces(), spaces()]), patch(
            "jarvis.workspace_control._inventory",
            side_effect=[[before], [before], [after]]), patch(
            "jarvis.workspace_control._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")) as dbus:
            result = move_window_to_workspace("XTerm", 2, lambda _: True)
        self.assertEqual(result["status"], "window_workspace_verified")
        dbus.assert_called_once_with("MoveToWorkspace", 17, 1)

    def test_move_rejects_ambiguity_sticky_and_changed_identity(self):
        with patch("jarvis.workspace_control._workspaces", return_value=spaces()), patch(
            "jarvis.workspace_control._inventory", return_value=[window(), window(ident=18)]), patch(
            "jarvis.workspace_control._dbus") as dbus:
            self.assertEqual(move_window_to_workspace("XTerm", 2, lambda _: True)["status"],
                             "ambiguous")
            dbus.assert_not_called()
        sticky = {**window(), "is_on_all_workspaces": True}
        with patch("jarvis.workspace_control._workspaces", return_value=spaces()), patch(
            "jarvis.workspace_control._inventory", return_value=[sticky]), patch(
            "jarvis.workspace_control._dbus") as dbus:
            self.assertEqual(move_window_to_workspace("XTerm", 2, lambda _: True)["status"],
                             "refused")
            dbus.assert_not_called()
        with patch("jarvis.workspace_control._workspaces", return_value=spaces()), patch(
            "jarvis.workspace_control._inventory",
            side_effect=[[window()], [window(ident=19)]]), patch(
            "jarvis.workspace_control._dbus") as dbus:
            self.assertEqual(move_window_to_workspace("XTerm", 2, lambda _: True)["status"],
                             "changed")
            dbus.assert_not_called()

    def test_move_never_claims_success_without_observed_change(self):
        with patch("jarvis.workspace_control._workspaces", return_value=spaces()), patch(
            "jarvis.workspace_control._inventory", return_value=[window()]), patch(
            "jarvis.workspace_control._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")):
            result = move_window_to_workspace("XTerm", 2, lambda _: True,
                                              retries=1)
        self.assertEqual(result["status"], "window_workspace_unverified")

    def test_router_toolkit_audit_and_local_reply(self):
        self.assertEqual([spec["name"] for spec in tool_catalog(
            "Jarvis, vá para a segunda área de trabalho", TOOL_SPECS)],
            ["activate_workspace"])
        self.assertEqual([spec["name"] for spec in tool_catalog(
            "Jarvis, mova o Firefox para a segunda área de trabalho", TOOL_SPECS)],
            ["move_window_to_workspace"])
        with tempfile.TemporaryDirectory() as tmp, patch(
                "jarvis.workspace_control.activate_workspace",
                return_value={"status": "workspace_verified", "workspace_number": 2}):
            kit = Toolkit(Path(tmp)/"workspace", approve=lambda _: True,
                          layout_db=Path(tmp)/"jarvis.db")
            result = kit.execute("activate_workspace", {"workspace_number": 2})
            history = kit.execute("window_action_history", {"limit": 1})
        self.assertEqual(result["audit_id"], 1)
        self.assertEqual(history["result"]["actions"][0]["details"],
                         {"workspace_number": 2})
        self.assertIn("confirmada pelo GNOME", _local_layout_reply(
            [{"name": "activate_workspace"}], [result]))


if __name__ == "__main__":
    unittest.main()
