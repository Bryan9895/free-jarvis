import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from jarvis.browser_tabs import BrowserTabs
from jarvis.tools import Toolkit


class Page:
    def __init__(self, context):
        self.context, self.url, self.closed = context, 'about:blank', False
        self.front = False
    def is_closed(self): return self.closed
    def title(self): return 'Teste'
    def goto(self, url, **kwargs): self.url = url
    def close(self, **kwargs): self.closed = True
    def bring_to_front(self): self.front = True

class Context:
    def __init__(self): self.pages = []
    def new_page(self):
        page = Page(self)
        self.pages.append(page)
        return page

class BrowserTabTests(unittest.TestCase):
    def test_ids_selection_and_external_close(self):
        context = Context()
        first = context.new_page()
        tabs = BrowserTabs(context, first)
        self.assertEqual(tabs.perform('tabs', {})['tabs'][0]['id'], 1)
        with patch('jarvis.browser_tabs.validate_url', side_effect=lambda x:x):
            new = tabs.perform('new_tab', {'url':'https://example.com'})
        self.assertEqual(new['tab_id'], 2)
        self.assertEqual(tabs.perform('select_tab', {'tab_id':1})['status'], 'observed')
        self.assertTrue(first.front)
        self.assertEqual(tabs.perform('close_tab', {'tab_id':1})['status'], 'closed_verified')
        self.assertEqual(tabs.perform('close_tab', {'tab_id':1})['status'], 'not_found')
        self.assertEqual(tabs.perform('tabs', {})['tabs'][0]['id'], 2)
        context.pages[1].close()
        self.assertEqual(tabs.perform('tabs', {})['tabs'], [])
        self.assertFalse(tabs.active_page().is_closed())
        self.assertEqual(tabs.perform('tabs', {})['tabs'][0]['id'], 3)

    def test_navigation_failure_does_not_leave_new_tab(self):
        context = Context()
        first = context.new_page()
        tabs = BrowserTabs(context, first)
        failed = Page(context)
        failed.goto = Mock(side_effect=RuntimeError('offline'))
        with patch.object(context, 'new_page', return_value=failed), patch(
                'jarvis.browser_tabs.validate_url', side_effect=lambda x:x):
            with self.assertRaises(RuntimeError):
                tabs.perform('new_tab', {'url':'https://example.com'})
        self.assertTrue(failed.closed)
        self.assertIs(tabs.current, first)

    def test_close_requires_sensitive_approval(self):
        with tempfile.TemporaryDirectory() as td:
            policy = Mock(return_value=True)
            policy.confirm_sensitive.return_value = False
            kit = Toolkit(Path(td), approve=policy)
            kit._browser = Mock()
            result = kit.execute('browser_close_tab', {'tab_id':1})
            self.assertEqual(result['result']['status'], 'rejected')
            kit._browser.perform.assert_not_called()
            kit.close()
