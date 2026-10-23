"""Abas com IDs estáveis na sessão Chromium gerenciada pelo Jarvis."""
from .browser_worker import validate_url


class BrowserTabs:
    def __init__(self, context, page):
        self.context = context
        self.current = page
        self.pages = {}
        self.next_id = 1

    def _sync(self):
        self.pages = {key: page for key, page in self.pages.items() if not page.is_closed()}
        for page in self.context.pages:
            if not page.is_closed() and page not in self.pages.values():
                self.pages[self.next_id] = page
                self.next_id += 1

    def perform(self, operation, args):
        self._sync()
        if operation == 'tabs':
            return {'status': 'listed', 'tabs': [
                {'id': key, 'url': page.url, 'title': page.title()[:200],
                 'active': page is self.current} for key, page in self.pages.items()]}
        if operation == 'new_tab':
            url = validate_url(args['url'])
            page = self.context.new_page()
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=20000)
                validate_url(page.url)
            except Exception:
                page.close()
                raise
            self.current = page
            self._sync()
            return {'status': 'loaded', 'tab_id': next(k for k,v in self.pages.items() if v is page),
                    'url': page.url}
        tab_id = args['tab_id']
        if type(tab_id) is not int or tab_id not in self.pages:
            return {'status': 'not_found'}
        page = self.pages[tab_id]
        if operation == 'select_tab':
            page.bring_to_front()
            self.current = page
            return {'status': 'observed', 'tab_id': tab_id, 'url': page.url}
        if operation == 'close_tab':
            page.close(run_before_unload=False)
            self._sync()
            if self.current is page:
                self.current = next(iter(self.pages.values()), None)
            return {'status': 'closed_verified' if page.is_closed() else 'close_unverified',
                    'tab_id': tab_id}
        raise ValueError('Operação de aba desconhecida')

    def active_page(self):
        self._sync()
        if self.current is None or self.current.is_closed():
            self.current = next(iter(self.pages.values()), None)
        if self.current is None:
            self.current = self.context.new_page()
        return self.current
