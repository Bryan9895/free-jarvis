"""Processo de automação. Não usa o perfil existente do Firefox do usuário."""
import ipaddress
import json
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

MAX_TEXT = 12000
MAX_ELEMENTS = 60

def validate_url(url):
    """Recusa protocolos internos, localhost e endpoints da rede local."""
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("URL inválida")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Somente URLs públicas HTTP/HTTPS são permitidas")
    host = parsed.hostname.rstrip(".").lower()
    if host in ("localhost",) or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Endereço local bloqueado")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(item[4][0])
                         for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]
        except OSError as exc:
            raise ValueError("Não foi possível resolver o domínio") from exc
    if not addresses or not all(ip.is_global for ip in addresses):
        raise ValueError("Endereço privado ou reservado bloqueado")
    return url

def _elements(page):
    return page.locator("a,button,input,textarea,select,[role='button']").evaluate_all(
        """nodes => nodes.slice(0,60).map(el => ({
          tag: el.tagName.toLowerCase(), text: (el.innerText || el.value || '').slice(0,100),
          role: el.getAttribute('role'), type: el.getAttribute('type'),
          placeholder: el.getAttribute('placeholder'), aria_label: el.getAttribute('aria-label')
        }))"""
    )

def handle(page, op, args, workspace):
    if op == "navigate":
        url = validate_url(args["url"])
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        validate_url(page.url)
        return {"url": page.url, "title": page.title()[:200], "status": "loaded"}
    if op == "inspect":
        return {"url": page.url, "title": page.title()[:200],
                "text": page.locator("body").inner_text(timeout=7000)[:MAX_TEXT],
                "elements": _elements(page)[:MAX_ELEMENTS]}
    if op in ("click", "fill"):
        selector = args["selector"]
        if not isinstance(selector, str) or len(selector) > 500:
            raise ValueError("Seletor inválido")
        target = page.locator(selector)
        if target.count() != 1:
            raise ValueError("Seletor deve corresponder a exatamente um elemento")
        if op == "click":
            before_url = page.url
            before_text = page.locator("body").inner_text(timeout=7000)[:MAX_TEXT]
            target.click(timeout=7000)
            popups = [popup for popup in page.context.pages if popup is not page]
            for popup in popups:
                popup.close()
        else:
            text = args["text"]
            if not isinstance(text, str) or len(text) > 2000:
                raise ValueError("Texto inválido")
            target.fill(text, timeout=7000)
        # Checar URL caso ação navegue; interceptação de rede também se aplica a redirects.
        if page.url.startswith(("http:", "https:")):
            validate_url(page.url)
        if op == "fill":
            observed = target.input_value(timeout=7000) == text
            return {"status": "filled_verified" if observed else "sent_unverified",
                    "url": page.url}
        after_text = page.locator("body").inner_text(timeout=7000)[:MAX_TEXT]
        return {"status": "executed", "url": page.url,
                "observed_change": page.url != before_url or after_text != before_text,
                "popups_closed": len(popups)}
    if op == "screenshot":
        target = workspace / "jarvis_screenshot.png"
        page.screenshot(path=str(target), full_page=False, timeout=10000)
        return {"status": "screenshot_verified" if target.is_file() and target.stat().st_size
                else "sent_unverified", "path": str(target)}
    raise ValueError("Operação desconhecida")

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"ok": False, "error": "Instale: pip install -e '.[browser]'"}), flush=True)
        return
    workspace = Path.cwd().resolve()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=False, service_workers="block")
        page = context.new_page()
        def check_route(route):
            try:
                validate_url(route.request.url)
                route.continue_()
            except ValueError:
                route.abort()
        context.route("**/*", check_route)
        try:
            for line in sys.stdin:
                try:
                    request = json.loads(line)
                    answer = handle(page, request["op"], request.get("args", {}), workspace)
                    response = {"ok": True, "result": answer}
                except Exception as exc:
                    response = {"ok": False, "error": str(exc)[:500]}
                print(json.dumps(response, ensure_ascii=False), flush=True)
        finally:
            browser.close()

if __name__ == "__main__":
    main()
