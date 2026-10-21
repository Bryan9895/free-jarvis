"""Playwright isolado em subprocesso, protocolo JSON-line em stdin/stdout."""
import json
import subprocess
import sys
from pathlib import Path
from threading import Lock

class BrowserError(RuntimeError):
    pass

class BrowserController:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.process = None
        self.lock = Lock()

    def _ensure_started(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.process = subprocess.Popen(
            [sys.executable, "-m", "jarvis.browser_worker"],
            cwd=str(self.workspace), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )

    def perform(self, operation: str, **kwargs):
        with self.lock:
            self._ensure_started()
            try:
                request = json.dumps({"op": operation, "args": kwargs}, ensure_ascii=False)
                self.process.stdin.write(request + "\n")
                self.process.stdin.flush()
                response = self.process.stdout.readline()
                if not response:
                    raise BrowserError("O processo do navegador encerrou inesperadamente")
                item = json.loads(response)
                if not item.get("ok"):
                    raise BrowserError(item.get("error", "Erro não identificado"))
                return item["result"]
            except (BrokenPipeError, OSError, ValueError) as exc:
                self.close()
                raise BrowserError("Falha na comunicação com o navegador") from exc

    def close(self):
        if self.process is not None:
            proc = self.process
            self.process = None
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
