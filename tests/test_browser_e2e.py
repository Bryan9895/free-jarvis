"""Integração com Chromium real, sem chamadas externas ou login."""
import tempfile
import unittest
from unittest.mock import patch
from jarvis.browser_tabs import BrowserTabs
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from jarvis.browser_worker import handle

@unittest.skipIf(sync_playwright is None, "Playwright não instalado")
class BrowserE2E(unittest.TestCase):
    def test_inspect_fill_click_and_screenshot(self):
        with tempfile.TemporaryDirectory() as td:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    context = browser.new_context()
                    page = context.new_page()
                    page.set_content("""
                      <html><head><title>Teste JARVIS</title></head>
                      <body>
                        <label for="task">Tarefa</label>
                        <input id="task" placeholder="Digite uma tarefa">
                        <button id="add" onclick="document.querySelector('#result').textContent =
                            document.querySelector('#task').value">Adicionar</button>
                        <p id="result"></p>
                      </body></html>
                    """)
                    before = handle(page, "inspect", {}, Path(td))
                    self.assertEqual(before["title"], "Teste JARVIS")
                    self.assertTrue(any(el["tag"] == "button" for el in before["elements"]))
                    filled = handle(page, "fill", {"selector": "#task", "text": "Criar JARVIS"}, Path(td))
                    self.assertEqual(filled["status"], "filled_verified")
                    clicked = handle(page, "click", {"selector": "#add"}, Path(td))
                    self.assertTrue(clicked["observed_change"])
                    self.assertIn("Criar JARVIS", handle(page, "inspect", {}, Path(td))["text"])
                    shot = handle(page, "screenshot", {}, Path(td))
                    self.assertEqual(shot["status"], "screenshot_verified")
                    self.assertTrue(Path(shot["path"]).is_file())
                    tabs = BrowserTabs(page.context, page)
                    first_id = tabs.perform("tabs", {})["tabs"][0]["id"]
                    page.context.route("https://tabs.example.test/**", lambda route: route.fulfill(
                        status=200, content_type="text/html", body="<title>Segunda aba</title><p>Teste</p>"))
                    with patch("jarvis.browser_tabs.validate_url", side_effect=lambda url: url):
                        second = tabs.perform("new_tab", {"url": "https://tabs.example.test/"})
                    tabs.perform("select_tab", {"tab_id": first_id})
                    handle(page, "click", {"selector": "#add"}, Path(td))
                    self.assertEqual(len(tabs.perform("tabs", {})["tabs"]), 2)
                    self.assertEqual(tabs.perform("close_tab", {"tab_id": second["tab_id"]})["status"],
                                     "closed_verified")
                    self.assertEqual(len(tabs.perform("tabs", {})["tabs"]), 1)
                finally:
                    browser.close()

if __name__ == "__main__":
    unittest.main()
