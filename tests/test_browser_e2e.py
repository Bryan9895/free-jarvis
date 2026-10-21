"""Integração com Chromium real, sem chamadas externas ou login."""
import tempfile
import unittest
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
                    page = browser.new_page()
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
                    handle(page, "fill", {"selector": "#task", "text": "Criar JARVIS"}, Path(td))
                    handle(page, "click", {"selector": "#add"}, Path(td))
                    self.assertIn("Criar JARVIS", handle(page, "inspect", {}, Path(td))["text"])
                    shot = handle(page, "screenshot", {}, Path(td))
                    self.assertTrue(Path(shot["path"]).is_file())
                finally:
                    browser.close()

if __name__ == "__main__":
    unittest.main()
