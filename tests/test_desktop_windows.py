"""Window observation tests without requiring a graphical session."""
import json
import unittest
from unittest.mock import Mock, patch

from jarvis.desktop_windows import desktop_windows, verify_app_window
from jarvis.tools import Toolkit, TOOL_SPECS
from pathlib import Path
import tempfile


class WindowTests(unittest.TestCase):
    def test_mocked_accessibility_response(self):
        payload={"status":"observed","windows":[
            {"app":"Code","title":"main.py - VS Code"},
            {"app":"Firefox","title":"Mozilla Firefox"}]}
        with patch.dict("os.environ",{"XDG_SESSION_TYPE":"wayland"}),patch(
            "jarvis.desktop_windows.subprocess.run",return_value=Mock(
                returncode=0,stdout=json.dumps(payload))):
            observed=desktop_windows()
            self.assertEqual(len(observed["windows"]),2)
            found=verify_app_window("Code","main.py")
            self.assertEqual(found["status"],"window_observed")
            absent=verify_app_window("LibreOffice")
            self.assertEqual(absent["status"],"not_observed")

    def test_unavailable_is_not_false_negative(self):
        with patch.dict("os.environ",{"XDG_SESSION_TYPE":"x11"}):
            self.assertEqual(verify_app_window("Code")["status"],"unavailable")

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            verify_app_window("../unsafe")
        with self.assertRaises(ValueError):
            verify_app_window("Code","x"*121)

    def test_tool_specs_exposed(self):
        with tempfile.TemporaryDirectory() as td:
            tool=Toolkit(Path(td))
            with patch.dict("os.environ",{"XDG_SESSION_TYPE":"x11"}):
                result=tool.execute("desktop_windows",{})
            self.assertEqual(result["result"]["status"],"unavailable")
            names={x["name"] for x in TOOL_SPECS}
            self.assertTrue({"desktop_windows","verify_app_window"}<=names)
            tool.close()


if __name__=="__main__":
    unittest.main()
