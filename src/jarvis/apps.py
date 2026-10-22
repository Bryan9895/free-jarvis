"""Descoberta local de aplicativos Linux via entradas XDG .desktop.

Nunca executa o campo Exec do arquivo .desktop. A inicialização é delegada ao
gtk-launch com identificador literal instalado e aprovação da operação.
"""
from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
from pathlib import Path

_ID = re.compile(r"[A-Za-z0-9_.+-]{1,160}\Z")
MAX_APPS = 800


def _directories():
    home = Path.home()
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share")))
    data_dirs = [Path(x) for x in os.environ.get(
        "XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if x]
    return [base.expanduser() / "applications" for base in [data_home, *data_dirs]]


def installed_applications(limit=80, query=""):
    if type(limit) is not int or not 1 <= limit <= 120:
        raise ValueError("Limite de aplicativos inválido")
    if not isinstance(query, str) or len(query) > 120:
        raise ValueError("Pesquisa de aplicativos inválida")
    lookup = query.casefold().strip()
    found = {}
    for directory in _directories():
        if not directory.is_dir():
            continue
        for desktop_file in sorted(directory.glob("*.desktop"))[:MAX_APPS]:
            app_id = desktop_file.name.removesuffix(".desktop")
            if app_id in found or not _ID.fullmatch(app_id):
                continue
            try:
                parser = configparser.ConfigParser(interpolation=None, strict=False)
                parser.optionxform = str
                parser.read(desktop_file, encoding="utf-8")
                if not parser.has_section("Desktop Entry"):
                    continue
                entry = parser["Desktop Entry"]
                if (entry.get("Type", "") != "Application"
                        or entry.get("Hidden", "false").lower() == "true"
                        or entry.get("NoDisplay", "false").lower() == "true"):
                    continue
                name = entry.get("Name", app_id).strip()
                if not name:
                    name = app_id
                if lookup and lookup not in name.casefold() and lookup not in app_id.casefold():
                    continue
                found[app_id] = {"id": app_id, "name": name[:120]}
            except (OSError, UnicodeError, configparser.Error):
                continue
    return sorted(found.values(), key=lambda x: (x["name"].casefold(), x["id"]))[:limit]


def launch_installed_app(app_id, approve):
    if not isinstance(app_id, str) or not _ID.fullmatch(app_id):
        raise ValueError("ID de aplicativo inválido")
    # Lista visível e não oculta, não executa um ID inventado pelo modelo.
    matches = [a for a in installed_applications(limit=120) if a["id"] == app_id]
    # Para catálogos maiores, pesquisa direcionada pelo identificador.
    if not matches:
        matches = [a for a in installed_applications(query=app_id, limit=120)
                   if a["id"] == app_id]
    if not matches:
        raise ValueError("Aplicativo não encontrado no catálogo XDG visível")
    launcher = shutil.which("gtk-launch")
    if not launcher:
        raise ValueError("gtk-launch indisponível; instale libgtk-3-bin")
    if not approve(f"ABRIR APLICATIVO {matches[0]['name']} ({app_id})?"):
        return {"status": "rejected"}
    # Revalida antes de acionar gtk-launch, após consentimento.
    if not any(x["id"] == app_id for x in installed_applications(query=app_id, limit=120)):
        raise ValueError("Aplicativo indisponível após autorização")
    process = subprocess.Popen([launcher, app_id], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    return {"status": "launched_unverified", "id": app_id, "pid": process.pid,
            "note": "O gtk-launch foi iniciado; não confirma abertura da janela."}
