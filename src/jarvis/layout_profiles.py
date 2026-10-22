"""Perfis de geometria de janelas existentes, persistidos no SQLite local."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .window_layout import (_identity_ok, _place_one, _placement_verified,
                            _select, _workarea)
from .window_manage import _inventory, EXTENSION_URL


def _name(value):
    if (not isinstance(value, str) or not 1 <= len(value.strip()) <= 60
            or any(ord(c) < 32 for c in value)):
        raise ValueError("Nome de perfil inválido")
    return value.strip()


def _store(db_path):
    if db_path is None:
        return None
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS window_layout_profiles ("
                       "name TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                       "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    return connection


def list_window_layouts(db_path):
    connection = _store(db_path)
    if connection is None:
        return {"status": "unavailable", "reason": "Banco de perfis não configurado"}
    try:
        rows = connection.execute("SELECT name, updated_at FROM window_layout_profiles "
                                  "ORDER BY name LIMIT 100").fetchall()
        return {"status": "listed", "profiles": [
            {"name": name, "updated_at": updated_at} for name, updated_at in rows]}
    finally:
        connection.close()


def save_window_layout(db_path, name, windows, approve):
    if db_path is None:
        return {"status": "unavailable", "reason": "Banco de perfis não configurado"}
    name = _name(name)
    if not isinstance(windows, list) or not 2 <= len(windows) <= 4:
        raise ValueError("Informe de duas a quatro janelas abertas")
    selectors = []
    for item in windows:
        if not isinstance(item, dict) or set(item) - {"app", "title"}:
            raise ValueError("Seletor de janela inválido")
        app, title = item.get("app"), item.get("title", "")
        if (not isinstance(app, str) or not 2 <= len(app) <= 100
                or not isinstance(title, str) or len(title) > 200
                or any(c in app + title for c in ("\n", "\r", "\x00"))):
            raise ValueError("Nome ou título de janela inválido")
        selectors.append((app, title))
    rows = _inventory()
    if rows is None:
        return {"status": "unavailable", "install_url": EXTENSION_URL}
    selected = []
    for app, title in selectors:
        row, error = _select(rows, app, title)
        if error:
            return {"status": error, "selector": {"app": app, "title": title}}
        selected.append(row)
    if len({row["id"] for row in selected}) != len(selected):
        return {"status": "ambiguous", "reason": "Seletores repetem uma janela"}
    monitor = selected[0].get("monitor")
    if type(monitor) is not int or monitor < 0 or any(
            row.get("monitor") != monitor for row in selected):
        return {"status": "unavailable", "reason": "Janelas precisam estar no mesmo monitor"}
    area = _workarea(monitor)
    if area is None:
        return {"status": "unavailable", "reason": "Área útil indisponível"}
    ax, ay, aw, ah = area
    entries = []
    for row in selected:
        rect = [row.get(key) for key in ("x", "y", "width", "height")]
        if (any(type(v) is not int for v in rect) or rect[2] < 100 or rect[3] < 100
                or rect[0] < ax or rect[1] < ay
                or rect[0] + rect[2] > ax + aw or rect[1] + rect[3] > ay + ah):
            return {"status": "unavailable", "reason": "Geometria fora da área útil"}
        entries.append({"app": row["app"], "title": row["title"],
                        "rect": [rect[0] - ax, rect[1] - ay, rect[2], rect[3]]})
    if not approve(f"SALVAR PERFIL DE JANELAS '{name}' com {len(entries)} janelas?"):
        return {"status": "rejected"}
    current = _inventory()
    if current is None or _workarea(monitor) != area:
        return {"status": "changed", "reason": "Área de trabalho mudou durante a autorização"}
    for old, entry in zip(selected, entries):
        now, error = _select(current, entry["app"], entry["title"])
        if (error or not _identity_ok(old, now)
                or [now.get(key) for key in ("x", "y", "width", "height")]
                != [entry["rect"][0] + ax, entry["rect"][1] + ay,
                    entry["rect"][2], entry["rect"][3]]):
            return {"status": "changed", "reason": "Janela mudou durante a autorização"}
    connection = _store(db_path)
    if connection is None:
        return {"status": "unavailable", "reason": "Banco de perfis não configurado"}
    try:
        payload = json.dumps({"workarea": [aw, ah], "windows": entries}, ensure_ascii=False)
        connection.execute("INSERT INTO window_layout_profiles(name,payload) VALUES (?,?) "
                           "ON CONFLICT(name) DO UPDATE SET payload=excluded.payload, "
                           "updated_at=CURRENT_TIMESTAMP", (name, payload))
        connection.commit()
    finally:
        connection.close()
    return {"status": "saved", "name": name, "windows": len(entries)}


def _scaled_rect(area, source_area, rect):
    ax, ay, aw, ah = area
    sw, sh = source_area
    if (not all(type(v) is int for v in (*source_area, *rect))
            or sw < 200 or sh < 200 or len(rect) != 4
            or rect[0] < 0 or rect[1] < 0 or rect[2] < 100 or rect[3] < 100
            or rect[0] + rect[2] > sw or rect[1] + rect[3] > sh):
        raise ValueError("Perfil de geometria inválido")
    x = ax + rect[0] * aw // sw
    y = ay + rect[1] * ah // sh
    width = rect[2] * aw // sw
    height = rect[3] * ah // sh
    if width < 100 or height < 100:
        raise ValueError("Área atual pequena demais para o perfil")
    return x, y, min(width, ax + aw - x), min(height, ay + ah - y)


def restore_window_layout(db_path, name, approve):
    name = _name(name)
    connection = _store(db_path)
    if connection is None:
        return {"status": "unavailable", "reason": "Banco de perfis não configurado"}
    try:
        row = connection.execute("SELECT payload FROM window_layout_profiles WHERE name=?",
                                 (name,)).fetchone()
    finally:
        connection.close()
    if row is None:
        return {"status": "not_found", "name": name}
    try:
        profile = json.loads(row[0])
        entries = profile["windows"]
        source_area = profile["workarea"]
        if not isinstance(entries, list) or not 2 <= len(entries) <= 4:
            raise ValueError("Quantidade de janelas inválida")
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Perfil salvo inválido") from exc
    before = _inventory()
    if before is None:
        return {"status": "unavailable", "install_url": EXTENSION_URL}
    selected = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Perfil salvo inválido")
        app, title = entry.get("app"), entry.get("title")
        if not isinstance(app, str) or not isinstance(title, str):
            raise ValueError("Perfil salvo inválido")
        chosen, error = _select(before, app, title)
        if error:
            return {"status": error, "app": app, "title": title}
        selected.append(chosen)
    if len({item["id"] for item in selected}) != len(selected):
        return {"status": "ambiguous", "reason": "Perfil aponta para a mesma janela"}
    monitor = selected[0].get("monitor")
    if type(monitor) is not int or monitor < 0 or any(
            item.get("monitor") != monitor for item in selected):
        return {"status": "unavailable", "reason": "Janelas precisam estar no mesmo monitor"}
    area = _workarea(monitor)
    if area is None:
        return {"status": "unavailable", "reason": "Área útil indisponível"}
    try:
        rects = [_scaled_rect(area, source_area, entry["rect"]) for entry in entries]
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Perfil salvo inválido ou incompatível") from exc
    if not approve(f"RESTAURAR PERFIL '{name}' com {len(selected)} janelas?"):
        return {"status": "rejected"}
    current = _inventory()
    if current is None:
        return {"status": "unavailable"}
    for entry, old in zip(entries, selected):
        now, error = _select(current, entry["app"], entry["title"])
        if error or not _identity_ok(old, now) or now.get("monitor") != monitor:
            return {"status": "changed", "reason": "Janela mudou antes da restauração"}
    outcomes = []
    for chosen, rect in zip(selected, rects):
        sent = _place_one(chosen, rect)
        status = ("geometry_verified" if sent and _placement_verified(chosen, rect)
                  else "geometry_unverified" if sent else "failed")
        outcomes.append({"app": chosen["app"], "title": chosen["title"], "status": status})
        if status == "failed":
            break
    if len(outcomes) == len(selected) and all(
            item["status"] == "geometry_verified" for item in outcomes):
        return {"status": "layout_verified", "name": name, "windows": outcomes}
    return {"status": "layout_unverified", "name": name, "outcomes": outcomes}
