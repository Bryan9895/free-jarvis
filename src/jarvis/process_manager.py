"""Abertura de projetos e monitoramento de processos iniciados pela JARVIS.

O registro acompanha o PROCESSO lançador, não garante a existência da janela
gráfica (VS Code/gtk-launch podem delegar a processos que já estavam rodando).
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path


_EDITORS = {
    "vscode": ("code", ["--new-window"]),
    "vscodium": ("codium", ["--new-window"]),
    "vscode-insiders": ("code-insiders", ["--new-window"]),
}
MAX_LAUNCHES = 100


class ProcessManager:
    def __init__(self):
        self._launched = []
        self._next_id = 1

    def open_project(self, directory: Path, editor: str, approve):
        """Abre projeto existente com editor conhecido; nunca usa shell."""
        if editor not in _EDITORS:
            raise ValueError("Editor desconhecido. Use vscode, vscodium ou vscode-insiders.")
        if not isinstance(directory, Path) or not directory.is_dir():
            raise ValueError("Diretório de projeto não existe")
        binary, options = _EDITORS[editor]
        executable = shutil.which(binary)
        if not executable:
            raise ValueError(f"Editor {binary} não está no PATH")
        if len(self._launched) >= MAX_LAUNCHES:
            raise ValueError("Limite de processos registrados na sessão")
        if not approve(f"ABRIR PROJETO {directory} no editor {editor}?"):
            return {"status": "rejected"}
        # A existência foi verificada antes e é conferida novamente.
        if not directory.is_dir():
            raise ValueError("A pasta do projeto deixou de existir")
        process = subprocess.Popen(
            [executable, *options, str(directory)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        launch_id = self._next_id
        self._next_id += 1
        self._launched.append({
            "id": launch_id, "editor": editor, "directory": str(directory),
            "pid": process.pid, "started_at": time.time(), "process": process
        })
        return {"status": "launched_unverified", "id": launch_id, "pid": process.pid,
                "directory": str(directory), "editor": editor,
                "note": "Início do lançador confirmado; janela/instância gráfica não verificada."}

    def list_launches(self):
        result = []
        for entry in self._launched:
            process = entry["process"]
            code = process.poll()
            result.append({
                "id": entry["id"], "editor": entry["editor"],
                "directory": entry["directory"], "pid": entry["pid"],
                "started_at": entry["started_at"],
                "launcher_status": "running" if code is None else "exited",
                "launcher_exit_code": code,
                "window_status": "unknown",
            })
        return result

    def close(self):
        # Não mata editores nem processos ao encerrar a JARVIS.
        self._launched.clear()
