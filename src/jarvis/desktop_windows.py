"""Read-only GNOME Wayland window checks from system AT-SPI worker."""
import json
import os
from pathlib import Path
import re
import subprocess

WORKER = Path(__file__).with_name("atspi_worker.py")
PYTHON = "/usr/bin/python3"


def desktop_windows():
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return {"status":"unavailable","reason":"Requer sessão Wayland","windows":[]}
    if not Path(PYTHON).is_file():
        return {"status":"unavailable","reason":"Python do sistema indisponível","windows":[]}
    try:
        proc = subprocess.run([PYTHON,str(WORKER)],capture_output=True,text=True,
                              timeout=6,check=False)
        if proc.returncode or len(proc.stdout)>100000:
            return {"status":"unavailable","reason":"Worker AT-SPI falhou","windows":[]}
        response=json.loads(proc.stdout)
        if not isinstance(response,dict) or not isinstance(response.get("windows"),list):
            raise ValueError("Resposta incorreta")
        return response
    except (OSError,subprocess.TimeoutExpired,ValueError):
        return {"status":"unavailable","reason":"Falha de consulta AT-SPI","windows":[]}


def verify_app_window(app, title=""):
    if not isinstance(app,str) or not 2<=len(app)<=100 or not re.fullmatch(r"[\w .+\-]+",app):
        raise ValueError("Nome de aplicativo inválido")
    if not isinstance(title,str) or len(title)>120:
        raise ValueError("Título inválido")
    data=desktop_windows()
    if data["status"]!="observed":
        return {"status":"unavailable","reason":data.get("reason","AT-SPI indisponível")}
    needle=app.casefold().strip()
    title_needle=title.casefold().strip()
    found=[w for w in data["windows"] if needle in w.get("app","").casefold()
           or needle in w.get("title","").casefold()]
    if title_needle:
        found=[w for w in found if title_needle in w.get("title","").casefold()]
    if found:
        return {"status":"window_observed","matches":found[:10],
                "note":"Janela exposta via acessibilidade; não comprova foco ou conteúdo"}
    return {"status":"not_observed","matches":[],
            "note":"Ausência na árvore AT-SPI não comprova que aplicativo está fechado"}
