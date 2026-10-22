"""Simula organização de janelas GNOME com Window Control, sem alterar desktop CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.window_layout import _half, _workarea, place_window, arrange_windows
from jarvis.tools import TOOL_SPECS, Toolkit
from jarvis.router import tool_catalog
from jarvis.agent import Agent
from jarvis.memory import Memory


def window(id, app, title, x=0, width=600):
    return {"id": id, "app": app, "title": title, "pid": id + 100,
            "monitor": 0, "x": x, "y": 0, "width": width, "height": 900,
            "is_minimized": False, "is_maximized": False}


class LayoutTests(unittest.TestCase):
    def test_real_window_control_nested_monitor_and_frame_rect(self):
        """Contrato real do ListDetailed: monitor_index e frame_rect."""
        import json
        from unittest.mock import Mock
        from jarvis.window_manage import _inventory
        def raw(id, app, title, x, width):
            return {"id": id, "wm_class": app, "title": title,
                    "pid": id + 100, "monitor_index": 0,
                    "frame_rect": {"x": x, "y": 32,
                                   "width": width, "height": 700},
                    "is_minimized": False, "is_maximized": False}
        firefox = raw(15, "firefox_firefox", "Mozilla Firefox", 0, 1300)
        vscode = raw(16, "code_code", "Visual Studio Code", 0, 1300)
        first = repr((json.dumps([firefox, vscode]),))
        moved_firefox = raw(15, "firefox_firefox", "Mozilla Firefox", 0, 650)
        moved_vscode = raw(16, "code_code", "Visual Studio Code", 650, 650)
        after_left = repr((json.dumps([moved_firefox, vscode]),))
        after_both = repr((json.dumps([moved_firefox, moved_vscode]),))
        state_calls = iter([first, first, after_left, after_both])
        def dbus(method, *args, **kwargs):
            if method == "ListDetailed":
                return Mock(returncode=0, stdout=next(state_calls))
            if method == "GetWorkarea":
                self.assertEqual(args, (0,))
                return Mock(returncode=0, stdout="(0, 32, 1300, 700)")
            if method == "MoveResize":
                return Mock(returncode=0, stdout="()")
            self.fail("Comando D-Bus inesperado: " + method)
        with patch("jarvis.window_manage._dbus", side_effect=dbus), patch(
                "jarvis.window_layout._dbus", side_effect=dbus):
            result = arrange_windows("firefox", "code", lambda _: True)
        self.assertEqual(result["status"], "layout_verified")
        self.assertEqual(_inventory.__module__, "jarvis.window_manage")

    def test_real_window_control_contract_maps_monitor_and_geometry(self):
        import json
        from unittest.mock import Mock
        from jarvis.window_manage import _inventory
        payload = {"id": 321, "wm_class": "code_code",
                   "title": "Visual Studio Code",
                   "monitor_index": 1, "pid": 100,
                   "frame_rect": {"x": 700, "y": 38,
                                  "width": 650, "height": 690},
                   "is_minimized": False, "is_maximized": False}
        with patch("jarvis.window_manage._dbus",
                   return_value=Mock(returncode=0,
                                     stdout=repr((json.dumps([payload]),)))):
            windows = _inventory()
        self.assertEqual(windows[0]["monitor"], 1)
        self.assertEqual([windows[0][k] for k in
                          ("x", "y", "width", "height")],
                         [700, 38, 650, 690])

    def test_half_geometry_preserves_odd_pixel(self):
        area = (5, 10, 1001, 800)
        self.assertEqual(_half(area, "left"), (5, 10, 500, 800))
        self.assertEqual(_half(area, "right"), (505, 10, 501, 800))

    def test_one_window_moves_and_verifies(self):
        old = window(15, "firefox_firefox", "Mozilla Firefox")
        new = window(15, "firefox_firefox", "Mozilla Firefox", x=500, width=500)
        with patch("jarvis.window_layout._inventory",
                   side_effect=[[old], [old], [new]]), patch(
            "jarvis.window_layout._workarea", return_value=(0, 0, 1000, 900)), patch(
            "jarvis.window_layout._run", return_value=True) as action:
            result = place_window("firefox", "right", lambda _: True)
        self.assertEqual(result["status"], "geometry_verified")
        action.assert_called_once_with("MoveResize", 15, 500, 0, 500, 900)

    def test_two_window_layout_verified(self):
        firefox = window(15, "firefox_firefox", "Mozilla Firefox")
        vscode = window(16, "code", "VS Code")
        left = window(15, "firefox_firefox", "Mozilla Firefox", width=500)
        right = window(16, "code", "VS Code", x=500, width=500)
        with patch("jarvis.window_layout._inventory",
                   side_effect=[[firefox, vscode], [firefox, vscode],
                                [left, right], [left, right]]), patch(
            "jarvis.window_layout._workarea", return_value=(0, 0, 1000, 900)), patch(
            "jarvis.window_layout._run", return_value=True) as action:
            result = arrange_windows("firefox", "code", lambda _: True)
        self.assertEqual(result["status"], "layout_verified")
        self.assertEqual([call.args for call in action.call_args_list], [
            ("MoveResize", 15, 0, 0, 500, 900),
            ("MoveResize", 16, 500, 0, 500, 900)])

    def test_ambiguous_and_missing_windows_do_nothing(self):
        firefox1 = window(15, "firefox_firefox", "Tab 1")
        firefox2 = window(16, "firefox_firefox", "Tab 2")
        with patch("jarvis.window_layout._inventory",
                   return_value=[firefox1, firefox2]), patch(
            "jarvis.window_layout._run") as run:
            result = place_window("firefox", "left", lambda _: True)
        self.assertEqual(result["status"], "ambiguous")
        run.assert_not_called()
        with patch("jarvis.window_layout._inventory", return_value=[firefox1]), patch(
            "jarvis.window_layout._run") as run:
            result = arrange_windows("firefox", "code", lambda _: True)
        self.assertEqual(result["status"], "not_observed")
        run.assert_not_called()

    def test_changed_identity_after_approval_rejected(self):
        old = window(15, "firefox_firefox", "Mozilla Firefox")
        replacement = window(19, "firefox_firefox", "Mozilla Firefox")
        with patch("jarvis.window_layout._inventory",
                   side_effect=[[old], [replacement]]), patch(
            "jarvis.window_layout._workarea", return_value=(0, 0, 1000, 900)), patch(
            "jarvis.window_layout._run") as run:
            result = place_window("firefox", "left", lambda _: True)
        self.assertEqual(result["status"], "changed")
        run.assert_not_called()

    def test_no_success_without_observed_geometry(self):
        old = window(15, "firefox_firefox", "Mozilla Firefox")
        with patch("jarvis.window_layout._inventory", return_value=[old]), patch(
            "jarvis.window_layout._workarea", return_value=(0, 0, 1000, 900)), patch(
            "jarvis.window_layout._run", return_value=True):
            result = place_window("firefox", "right", lambda _: True)
        self.assertEqual(result["status"], "geometry_unverified")

    def test_tool_registration_and_catalog_for_layout(self):
        names = {s["name"] for s in TOOL_SPECS}
        self.assertIn("place_window", names)
        self.assertIn("arrange_windows", names)
        self.assertEqual([s["name"] for s in tool_catalog(
            "Coloque Firefox na metade esquerda da tela", TOOL_SPECS)],
            ["place_window"])
        self.assertEqual([s["name"] for s in tool_catalog(
            "Coloque Firefox e VS Code lado a lado", TOOL_SPECS)],
            ["arrange_windows"])

    def test_layout_reply_does_not_request_second_model_round(self):
        class Client:
            active_model = "fake"
            def __init__(self):
                self.calls = []
            def responses(self, payload):
                self.calls.append(payload)
                return {"output": [{"type": "function_call",
                                    "name": "place_window", "call_id": "x",
                                    "arguments": '{"app":"firefox","position":"left"}'}]}
        with tempfile.TemporaryDirectory() as tmp:
            client = Client()
            memory = Memory(Path(tmp) / "mem.db")
            toolkit = Toolkit(Path(tmp))
            with patch.object(toolkit, "execute", return_value={"result": {
                "status": "geometry_verified", "position": "left",
                "title": "Mozilla Firefox"}}):
                agent = Agent(client, toolkit, memory, "fake")
                answer = agent.ask("Coloque Firefox na metade esquerda da tela")
            self.assertIn("geometria confirmada", answer)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(agent.last_metrics["tools_advertised"], 1)
            memory.close()


if __name__ == "__main__":
    unittest.main()
