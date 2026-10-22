"""GNOME Window Control regressions; no desktop mutation in CI."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.window_manage import manage_window, close_window, focused_window, _inventory
from jarvis.approval import ApprovalPolicy
from jarvis.tools import TOOL_SPECS, Toolkit
from jarvis.router import tool_catalog
from jarvis.agent import Agent
from jarvis.memory import Memory


def win(id=17, title="Página — Firefox", app="firefox_firefox",
        minimized=False, maximized=False, pid=42):
    return {"id": id, "title": title, "app": app, "pid": pid,
            "is_minimized": minimized, "is_maximized": maximized}


class WindowManageTests(unittest.TestCase):
    def test_focused_window_requires_matching_inventory(self):
        with patch("jarvis.window_manage._dbus",
                   return_value=Mock(returncode=0, stdout="(17, 'Página — Firefox', 'firefox_firefox')")), patch(
            "jarvis.window_manage._inventory", return_value=[win()]):
            self.assertEqual(focused_window()["status"], "focused_verified")
        with patch("jarvis.window_manage._dbus",
                   return_value=Mock(returncode=0, stdout="(17, 'Outro', 'firefox_firefox')")), patch(
            "jarvis.window_manage._inventory", return_value=[win()]):
            self.assertEqual(focused_window()["status"], "unverified")

    def test_close_revalidates_identity_and_observes_disappearance(self):
        before = [win()]
        with patch("jarvis.window_manage._inventory",
                   side_effect=[before, before, []]), patch(
            "jarvis.window_manage._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")) as dbus:
            result = close_window("firefox", "", lambda _: True)
        self.assertEqual(result["status"], "closed_verified")
        dbus.assert_called_once_with("Close", 17)

    def test_close_requires_specific_confirmation_even_in_auto_mode(self):
        prompts = []
        policy = ApprovalPolicy(auto=True, manual_callback=lambda msg: prompts.append(msg) or False,
                                report=lambda _: None)
        with patch("jarvis.window_manage._inventory", return_value=[win()]), patch(
            "jarvis.window_manage._dbus") as dbus:
            result = close_window("firefox", "", policy)
        self.assertEqual(result["status"], "rejected")
        self.assertIn("FECHAR JANELA", prompts[0])
        self.assertEqual(policy.auto_approved, 0)
        dbus.assert_not_called()

    def test_close_ambiguity_and_unsaved_dialog_are_not_success(self):
        with patch("jarvis.window_manage._inventory", return_value=[win(id=17), win(id=18)]), patch(
            "jarvis.window_manage._dbus") as dbus:
            self.assertEqual(close_window("firefox", "", lambda _: True)["status"], "ambiguous")
            dbus.assert_not_called()
        with patch("jarvis.window_manage._inventory", return_value=[win()]), patch(
            "jarvis.window_manage._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")):
            result = close_window("firefox", "", lambda _: True, retries=1)
        self.assertEqual(result["status"], "close_unverified")

    def test_maximize_requires_identity_and_verifies_new_state(self):
        before = [win()]
        after = [win(maximized=True)]
        approvals = []
        with patch("jarvis.window_manage._inventory",
                   side_effect=[before, before, after]), patch(
            "jarvis.window_manage._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")) as dbus:
            result = manage_window("firefox", "", "maximize",
                                   lambda prompt: approvals.append(prompt) or True)
        self.assertEqual(result["status"], "state_verified")
        self.assertEqual(dbus.call_args.args, ("Maximize", 17))
        self.assertEqual(len(approvals), 1)

    def test_minimize_and_restore_state(self):
        for action, initial, target in [
            ("minimize", False, True), ("restore", True, False),
            ("unmaximize", True, False)]:
            with self.subTest(action=action):
                before = win(minimized=initial) if action != "unmaximize" else win(maximized=True)
                after = win(minimized=target) if action != "unmaximize" else win(maximized=False)
                with patch("jarvis.window_manage._inventory",
                           side_effect=[[before], [before], [after]]), patch(
                    "jarvis.window_manage._dbus",
                    return_value=Mock(returncode=0, stdout="(true,)")):
                    result = manage_window("firefox", "", action, lambda _: True)
                self.assertEqual(result["status"], "state_verified")

    def test_ambiguous_and_rejected_do_not_send_control(self):
        with patch("jarvis.window_manage._inventory",
                   return_value=[win(id=17), win(id=18)]), patch(
            "jarvis.window_manage._dbus") as control:
            result = manage_window("firefox", "", "maximize", lambda _: True)
            self.assertEqual(result["status"], "ambiguous")
            control.assert_not_called()
        with patch("jarvis.window_manage._inventory", return_value=[win()]), patch(
            "jarvis.window_manage._dbus") as control:
            result = manage_window("firefox", "", "maximize", lambda _: False)
            self.assertEqual(result["status"], "rejected")
            control.assert_not_called()

    def test_window_changed_after_consent_is_not_acted_on(self):
        with patch("jarvis.window_manage._inventory",
                   side_effect=[[win()], [win(id=99)]]), patch(
            "jarvis.window_manage._dbus") as control:
            result = manage_window("firefox", "", "maximize", lambda _: True)
            self.assertEqual(result["status"], "changed")
            control.assert_not_called()

    def test_missing_extension_and_unverified_are_truthful(self):
        with patch("jarvis.window_manage._inventory", return_value=None):
            result = manage_window("firefox", "", "minimize", lambda _: True)
            self.assertEqual(result["status"], "unavailable")
            self.assertIn("window-control", result["install_url"])
        with patch("jarvis.window_manage._inventory", return_value=[win()]), patch(
            "jarvis.window_manage._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")):
            result = manage_window("firefox", "", "maximize", lambda _: True, retries=1)
            self.assertEqual(result["status"], "state_unverified")


    def test_maximized_but_minimized_firefox_must_restore_and_activate(self):
        before = [win(minimized=True, maximized=True)]
        after = [win(minimized=False, maximized=True)]
        with patch("jarvis.window_manage._inventory",
                   side_effect=[before, before, after]), patch(
            "jarvis.window_manage._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")) as dbus:
            result = manage_window("firefox", "", "maximize", lambda _: True)
        self.assertEqual(result["status"], "state_verified")
        self.assertEqual([call.args[0] for call in dbus.call_args_list],
                         ["Unminimize", "Activate"])

    def test_minimized_maximize_does_not_claim_success_if_still_hidden(self):
        before = [win(minimized=True, maximized=True)]
        with patch("jarvis.window_manage._inventory",
                   return_value=before), patch(
            "jarvis.window_manage._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")):
            result = manage_window("firefox", "", "maximize",
                                   lambda _: True, retries=1)
        self.assertEqual(result["status"], "state_unverified")

    def test_terminal_alias_finds_ptyxis_or_reports_ambiguity(self):
        with patch("jarvis.window_manage._inventory",
                   return_value=[win(app="org.gnome.Ptyxis",
                                     title="Terminal JARVIS")]), patch(
            "jarvis.window_manage._dbus",
            return_value=Mock(returncode=0, stdout="(true,)")):
            result = manage_window("terminal", "", "maximize",
                                   lambda _: True, retries=1)
        self.assertEqual(result["status"], "state_unverified")
        with patch("jarvis.window_manage._inventory",
                   return_value=[win(id=1, app="org.gnome.Ptyxis"),
                                 win(id=2, app="org.gnome.Ptyxis")]), patch(
            "jarvis.window_manage._dbus") as dbus:
            result = manage_window("terminal", "", "maximize", lambda _: True)
        self.assertEqual(result["status"], "ambiguous")
        dbus.assert_not_called()

    def test_preexisting_state_is_noop(self):
        with patch("jarvis.window_manage._inventory",
                   return_value=[win(maximized=True)]), patch(
            "jarvis.window_manage._dbus") as control:
            result = manage_window("firefox", "", "maximize", lambda _: True)
            self.assertEqual(result["status"], "already_in_state")
            control.assert_not_called()

    def test_parse_dbus_detailed_response(self):
        import json
        reply = repr((json.dumps([{"id": 17, "wm_class": "firefox_firefox",
                                   "title": "Firefox", "is_maximized": True}]),))
        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland"}), patch(
            "jarvis.window_manage._dbus",
            return_value=Mock(returncode=0, stdout=reply)):
            state = _inventory()
        self.assertEqual(state[0]["id"], 17)
        self.assertEqual(state[0]["app"], "firefox_firefox")

    def test_capability_router_and_tool_registration(self):
        self.assertIn("manage_window", {s["name"] for s in TOOL_SPECS})
        self.assertIn("close_window", {s["name"] for s in TOOL_SPECS})
        self.assertIn("focused_window", {s["name"] for s in TOOL_SPECS})
        self.assertEqual([s["name"] for s in tool_catalog(
            "Jarvis, maximize a janela do Firefox", TOOL_SPECS)],
            ["manage_window"])
        self.assertEqual([s["name"] for s in tool_catalog(
            "Jarvis, feche a janela do Firefox", TOOL_SPECS)], ["close_window"])
        self.assertEqual([s["name"] for s in tool_catalog(
            "Qual janela está em foco?", TOOL_SPECS)], ["focused_window"])
        with tempfile.TemporaryDirectory() as directory:
            kit = Toolkit(Path(directory))
            with patch("jarvis.window_manage._inventory", return_value=None):
                result = kit.execute("manage_window", {
                    "app": "firefox", "action": "minimize"})
            self.assertEqual(result["result"]["status"], "unavailable")
            kit.close()

    def test_agent_single_operation_has_no_second_model_call(self):
        class Client:
            active_model = "fake"
            def __init__(self):
                self.calls = []
            def responses(self, payload):
                self.calls.append(payload)
                return {"output": [{
                    "type": "function_call", "name": "manage_window",
                    "call_id": "manage-1",
                    "arguments": '{"app":"firefox","action":"maximize"}'
                }]}
        with tempfile.TemporaryDirectory() as directory:
            client = Client()
            memory = Memory(Path(directory) / "m.db")
            kit = Toolkit(Path(directory))
            with patch.object(kit, "execute", return_value={"result": {
                "status": "state_verified", "action": "maximize",
                "title": "Firefox"}}):
                agent = Agent(client, kit, memory, "fake")
                answer = agent.ask("Maximize a janela do Firefox")
            self.assertIn("confirmado pelo GNOME", answer)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(agent.last_metrics["tools_advertised"], 1)
            memory.close()


if __name__ == "__main__":
    unittest.main()
