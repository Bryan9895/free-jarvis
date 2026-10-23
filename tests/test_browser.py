"""Testes da etapa 3 sem rede nem navegador real."""
import unittest
import tempfile
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from jarvis.tools import Toolkit
from jarvis.browser_worker import validate_url
from jarvis.browser import BrowserController, BrowserError

class BrowserTests(unittest.TestCase):
    def test_block_unsafe_urls(self):
        for url in ("file:///etc/passwd", "javascript:alert(1)", "http://127.0.0.1/",
                    "http://localhost/", "http://192.168.1.2/", "http://[::1]/",
                    "http://user:password@example.com/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_navigation_requires_approval(self):
        with tempfile.TemporaryDirectory() as td:
            kit = Toolkit(Path(td), approve=lambda _: False)
            with patch("jarvis.browser_worker.validate_url", return_value="https://example.com"):
                result = kit.browser_navigate("https://example.com")
            self.assertEqual(result["status"], "rejected")
            self.assertIsNone(kit._browser)

    def test_fill_click_and_screenshot_require_approval(self):
        with tempfile.TemporaryDirectory() as td:
            kit = Toolkit(Path(td), approve=lambda _: False)
            for name, params in (("browser_click", {"selector":"button"}),
                                 ("browser_fill", {"selector":"input","text":"hello"}),
                                 ("browser_screenshot", {})):
                self.assertEqual(kit.execute(name, params)["result"]["status"], "rejected")
            self.assertIsNone(kit._browser)

    def test_approved_browser_calls_worker(self):
        with tempfile.TemporaryDirectory() as td:
            kit = Toolkit(Path(td), approve=lambda _: True)
            worker = MagicMock()
            kit._browser = worker
            self.assertEqual(kit.execute("browser_click", {"selector":"#ok"})["result"],
                             worker.perform.return_value)
            worker.perform.assert_called_once_with("click", selector="#ok")
            kit.close()
            worker.close.assert_called_once()

    def test_browser_specs_exist(self):
        from jarvis.tools import TOOL_SPECS
        names = {spec["name"] for spec in TOOL_SPECS}
        self.assertTrue({"browser_navigate","browser_inspect","browser_click","browser_fill",
                         "browser_screenshot"} <= names)

    def test_worker_timeout_closes_unresponsive_process(self):
        with tempfile.TemporaryDirectory() as td:
            worker = BrowserController(Path(td), timeout=0.05)
            worker.process = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True)
            with self.assertRaisesRegex(BrowserError, "Tempo limite"):
                worker.perform("inspect")
            self.assertIsNone(worker.process)

if __name__ == "__main__":
    unittest.main()
