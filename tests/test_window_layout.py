"""Simula organização de janelas GNOME com Window Control, sem alterar desktop CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.window_layout import (_half, _rectangle, _grid_rectangles, _workarea,
                                  place_window, arrange_windows, arrange_window_grid)
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
    def test_grid_rectangles_cover_area_without_overlap(self):
        area = (10, 20, 1001, 801)
        for count in (3, 4):
            with self.subTest(count=count):
                cells = _grid_rectangles(area, count)
                self.assertEqual(len(cells), count)
                self.assertEqual(sum(w * h for _, _, w, h in cells), 1001 * 801)
                self.assertTrue(all(10 <= x and 20 <= y and x + w <= 1011
                                    and y + h <= 821 for x, y, w, h in cells))

    def test_three_window_grid_sends_and_verifies_each_placement(self):
        original = [window(1, "code", "Code"), window(2, "firefox", "Firefox"),
                    window(3, "ptyxis", "Terminal")]
        placed = []
        for old, rect in zip(original, _grid_rectangles((0, 0, 1000, 800), 3)):
            updated = {**old, "x": rect[0], "y": rect[1],
                       "width": rect[2], "height": rect[3]}
            placed.append(updated)
        selectors = [{"app": item["app"]} for item in original]
        with patch("jarvis.window_layout._inventory",
                   side_effect=[original, original, [placed[0], *original[1:]],
                                [*placed[:2], original[2]], placed]), patch(
            "jarvis.window_layout._workarea", return_value=(0, 0, 1000, 800)), patch(
            "jarvis.window_layout._run", return_value=True) as run:
            result = arrange_window_grid(selectors, lambda _: True)
        self.assertEqual(result["status"], "layout_verified")
        self.assertEqual(len(run.call_args_list), 3)

    def test_grid_refuses_duplicate_and_changed_windows(self):
        original = [window(1, "code", "Code"), window(2, "firefox", "Firefox"),
                    window(3, "ptyxis", "Terminal")]
        with patch("jarvis.window_layout._inventory", return_value=original), patch(
            "jarvis.window_layout._workarea", return_value=(0, 0, 1000, 800)), patch(
            "jarvis.window_layout._run") as run:
            result = arrange_window_grid([{"app": "code"}, {"app": "code"},
                                          {"app": "firefox"}], lambda _: True)
            self.assertEqual(result["status"], "ambiguous")
            run.assert_not_called()
        changed = [*original[:2], window(4, "ptyxis", "Terminal")]
        with patch("jarvis.window_layout._inventory", side_effect=[original, changed]), patch(
            "jarvis.window_layout._workarea", return_value=(0, 0, 1000, 800)), patch(
            "jarvis.window_layout._run") as run:
            result = arrange_window_grid([{"app": "code"}, {"app": "firefox"},
                                          {"app": "ptyxis"}], lambda _: True)
            self.assertEqual(result["status"], "changed")
            run.assert_not_called()

    def test_half_geometry_preserves_odd_pixel(self):
        area = (5, 10, 1001, 800)
        self.assertEqual(_half(area, "left"), (5, 10, 500, 800))
        self.assertEqual(_half(area, "right"), (505, 10, 501, 800))

    def test_center_corner_and_percentage_stay_inside_workarea(self):
        area = (1920, 30, 1000, 900)
        current = window(15, "code", "VS Code", width=600)
        current["height"] = 400
        self.assertEqual(_rectangle(area, "center", current), (2120, 280, 600, 400))
        self.assertEqual(_rectangle(area, "bottom_right", current), (2420, 480, 500, 450))
        self.assertEqual(_rectangle(area, "center", current, 70, 100),
                         (2070, 30, 700, 900))
        with self.assertRaises(ValueError):
            _rectangle(area, "center", current, 101, None)

    def test_custom_pixels_are_relative_to_workarea_and_bounded(self):
        area = (1920, 30, 1000, 900)
        current = window(15, "code", "VS Code")
        self.assertEqual(_rectangle(area, "custom", current,
                                    x_px=100, y_px=50, width_px=700, height_px=600),
                         (2020, 80, 700, 600))
        for rect in ((900, 0, 200, 200), (-1, 0, 200, 200),
                     (0, 0, 99, 200), (0, 850, 200, 100)):
            with self.subTest(rect=rect), self.assertRaises(ValueError):
                _rectangle(area, "custom", current, x_px=rect[0], y_px=rect[1],
                           width_px=rect[2], height_px=rect[3])
        with self.assertRaises(ValueError):
            _rectangle(area, "left", current, x_px=0)

    def test_custom_position_is_sent_and_verified(self):
        old = window(15, "code", "VS Code")
        after = {**old, "x": 250, "y": 100, "width": 500, "height": 400}
        with patch("jarvis.window_layout._inventory",
                   side_effect=[[old], [old], [after]]), patch(
            "jarvis.window_layout._workarea", return_value=(100, 20, 1000, 900)), patch(
            "jarvis.window_layout._run", return_value=True) as action:
            result = place_window("code", "custom", lambda _: True,
                                  x_px=150, y_px=80, width_px=500, height_px=400)
        self.assertEqual(result["status"], "geometry_verified")
        action.assert_called_once_with("MoveResize", 15, 250, 100, 500, 400)

    def test_center_position_is_sent_and_verified(self):
        old = window(15, "code", "VS Code")
        after = window(15, "code", "VS Code", x=150, width=700)
        after["y"] = 0
        with patch("jarvis.window_layout._inventory",
                   side_effect=[[old], [old], [after]]), patch(
            "jarvis.window_layout._workarea", return_value=(0, 0, 1000, 900)), patch(
            "jarvis.window_layout._run", return_value=True) as action:
            result = place_window("code", "center", lambda _: True,
                                  width_percent=70, height_percent=100)
        self.assertEqual(result["status"], "geometry_verified")
        action.assert_called_once_with("MoveResize", 15, 150, 0, 700, 900)

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
        self.assertIn("arrange_window_grid", names)
        self.assertEqual([s["name"] for s in tool_catalog(
            "Coloque Firefox na metade esquerda da tela", TOOL_SPECS)],
            ["place_window"])
        self.assertEqual([s["name"] for s in tool_catalog(
            "Coloque Firefox e VS Code lado a lado", TOOL_SPECS)],
            ["arrange_windows"])
        self.assertEqual([s["name"] for s in tool_catalog(
            "Centralize o Firefox", TOOL_SPECS)], ["place_window"])
        self.assertEqual([s["name"] for s in tool_catalog(
            "Deixe o VS Code ocupando 70% da tela", TOOL_SPECS)], ["place_window"])
        self.assertEqual([s["name"] for s in tool_catalog(
            "Coloque Firefox em x=100, y=50 com 700 por 600 pixels", TOOL_SPECS)],
            ["place_window"])
        self.assertEqual([s["name"] for s in tool_catalog(
            "Organize três janelas em grade", TOOL_SPECS)], ["arrange_window_grid"])

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
