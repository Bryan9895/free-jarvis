"""Movimento multimonitor simulado, sem alterar o desktop do CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.agent import _local_layout_reply
from jarvis.monitor_control import move_window_to_monitor
from jarvis.router import tool_catalog
from jarvis.tools import TOOL_SPECS, Toolkit


def monitor(index, x):
    return {"index": index, "x": x, "y": 0, "width": 1000,
            "height": 800, "scale": 1, "connector": f"MON-{index}",
            "is_primary": index == 0}


MONITORS = [monitor(0, 0), monitor(1, 1000)]


def window(index=0, ident=17):
    return {"id": ident, "app": "XTerm", "title": "Disposable", "pid": 1234,
            "monitor": index}


class MonitorControlTests(unittest.TestCase):
    def test_move_to_unique_other_monitor_and_verify(self):
        with patch("jarvis.monitor_control._monitors", return_value=MONITORS), patch(
            "jarvis.monitor_control._inventory",
            side_effect=[[window()], [window()], [window(1)]]), patch(
            "jarvis.monitor_control._sent", return_value="sent") as sent:
            result = move_window_to_monitor("XTerm", lambda _: True)
        self.assertEqual(result["status"], "window_monitor_verified")
        self.assertEqual(result["monitor_number"], 2)
        sent.assert_called_once_with("MoveToMonitor", 17, 1)

    def test_not_found_ambiguous_and_already_on_monitor(self):
        with patch("jarvis.monitor_control._monitors", return_value=[MONITORS[0]]), patch(
            "jarvis.monitor_control._inventory", return_value=[window()]), patch(
            "jarvis.monitor_control._sent") as sent:
            self.assertEqual(move_window_to_monitor("XTerm", lambda _: True)["status"],
                             "not_found")
            self.assertEqual(move_window_to_monitor("XTerm", lambda _: True, 2)["status"],
                             "not_found")
            self.assertEqual(move_window_to_monitor("XTerm", lambda _: True, 1)["status"],
                             "already_in_state")
            sent.assert_not_called()
        with patch("jarvis.monitor_control._monitors",
                   return_value=[*MONITORS, monitor(2, 2000)]), patch(
            "jarvis.monitor_control._inventory", return_value=[window()]):
            self.assertEqual(move_window_to_monitor("XTerm", lambda _: True)["status"],
                             "ambiguous")
        with self.assertRaises(ValueError):
            move_window_to_monitor("XTerm", lambda _: True, True)

    def test_rejects_changed_topology_or_window_after_approval(self):
        with patch("jarvis.monitor_control._monitors",
                   side_effect=[MONITORS, [MONITORS[0], monitor(1, 1100)]]), patch(
            "jarvis.monitor_control._inventory", return_value=[window()]), patch(
            "jarvis.monitor_control._sent") as sent:
            self.assertEqual(move_window_to_monitor("XTerm", lambda _: True, 2)["status"],
                             "changed")
            sent.assert_not_called()
        with patch("jarvis.monitor_control._monitors", return_value=MONITORS), patch(
            "jarvis.monitor_control._inventory",
            side_effect=[[window()], [window(ident=19)]]), patch(
            "jarvis.monitor_control._sent") as sent:
            self.assertEqual(move_window_to_monitor("XTerm", lambda _: True, 2)["status"],
                             "changed")
            sent.assert_not_called()

    def test_never_claims_unobserved_move_or_wrong_target(self):
        with patch("jarvis.monitor_control._monitors", return_value=MONITORS), patch(
            "jarvis.monitor_control._inventory", return_value=[window()]), patch(
            "jarvis.monitor_control._sent", return_value="sent"):
            result = move_window_to_monitor("XTerm", lambda _: True, 2, retries=1)
        self.assertEqual(result["status"], "window_monitor_unverified")
        with patch("jarvis.monitor_control._monitors",
                   side_effect=[MONITORS, MONITORS,
                                [MONITORS[0], monitor(1, 1100)]]), patch(
            "jarvis.monitor_control._inventory",
            side_effect=[[window()], [window()], [window(1)]]), patch(
            "jarvis.monitor_control._sent", return_value="sent"):
            result = move_window_to_monitor("XTerm", lambda _: True, 2)
        self.assertEqual(result["status"], "window_monitor_unverified")

    def test_permission_routing_toolkit_and_audit(self):
        with patch("jarvis.monitor_control._monitors", return_value=MONITORS), patch(
            "jarvis.monitor_control._inventory", return_value=[window()]), patch(
            "jarvis.monitor_control._sent") as sent:
            self.assertEqual(move_window_to_monitor("XTerm", lambda _: False, 2)["status"],
                             "rejected")
            sent.assert_not_called()
        for prompt in ("Jarvis, coloque o terminal no outro monitor",
                       "Jarvis, mova o Firefox para o monitor 2"):
            with self.subTest(prompt=prompt):
                self.assertEqual([spec["name"] for spec in tool_catalog(prompt, TOOL_SPECS)],
                                 ["move_window_to_monitor"])
        with tempfile.TemporaryDirectory() as tmp, patch(
                "jarvis.monitor_control.move_window_to_monitor",
                return_value={"status": "window_monitor_verified", "monitor_number": 2}):
            kit = Toolkit(Path(tmp)/"workspace", approve=lambda _: True,
                          layout_db=Path(tmp)/"jarvis.db")
            result = kit.execute("move_window_to_monitor",
                                 {"app": "XTerm", "monitor_number": 2,
                                  "title": "Sensitive title"})
            history = kit.execute("window_action_history", {"limit": 1})
        self.assertEqual(result["audit_id"], 1)
        details = history["result"]["actions"][0]["details"]
        self.assertEqual(details, {"app": "XTerm", "monitor_number": 2})
        self.assertIn("confirmado pelo GNOME", _local_layout_reply(
            [{"name": "move_window_to_monitor"}], [result]))


if __name__ == "__main__":
    unittest.main()
