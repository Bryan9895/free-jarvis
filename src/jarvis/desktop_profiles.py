"""Perfis de ambiente GNOME: aplicativos, monitores, áreas e geometria."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .apps import _ID, launch_installed_app
from .desktop_spaces import _monitors, _workspaces
from .layout_profiles import _name, _scaled_rect
from .monitor_control import move_window_to_monitor
from .window_layout import _identity_ok, _select, _workarea, place_window
from .window_manage import _inventory, EXTENSION_URL
from .workspace_control import activate_workspace, move_window_to_workspace


def _connection(db_path):
    if db_path is None:
        return None
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS desktop_profiles ("
                       "name TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                       "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    connection.execute("CREATE TABLE IF NOT EXISTS desktop_profile_launches ("
                       "profile_name TEXT NOT NULL, entry_index INTEGER NOT NULL, "
                       "PRIMARY KEY(profile_name, entry_index))")
    return connection


def _pending(db_path, name, entry_index):
    connection = _connection(db_path)
    try:
        return connection.execute(
            "SELECT 1 FROM desktop_profile_launches WHERE profile_name=? AND entry_index=?",
            (name, entry_index)).fetchone() is not None
    finally:
        connection.close()


def _set_pending(db_path, name, entry_index, pending):
    connection = _connection(db_path)
    try:
        if pending:
            connection.execute("INSERT OR IGNORE INTO desktop_profile_launches "
                               "(profile_name,entry_index) VALUES (?,?)", (name, entry_index))
        else:
            connection.execute("DELETE FROM desktop_profile_launches "
                               "WHERE profile_name=? AND entry_index=?", (name, entry_index))
        connection.commit()
    finally:
        connection.close()


def _selectors(windows):
    if not isinstance(windows, list) or not 1 <= len(windows) <= 4:
        raise ValueError("Informe de uma a quatro janelas")
    result = []
    for item in windows:
        if not isinstance(item, dict) or set(item) - {"app", "title", "app_id"}:
            raise ValueError("Seletor de janela inválido")
        app, title, app_id = item.get("app"), item.get("title", ""), item.get("app_id")
        if (not isinstance(app, str) or not 2 <= len(app) <= 100
                or not isinstance(title, str) or len(title) > 200
                or any(ord(c) < 32 for c in app + title)
                or app_id is not None and (not isinstance(app_id, str)
                                           or not _ID.fullmatch(app_id))):
            raise ValueError("Aplicativo, título ou ID XDG inválido")
        result.append({"app": app, "title": title, "app_id": app_id})
    return result


def _monitor_for(row, monitors):
    return next((item for item in monitors if item["index"] == row.get("monitor")), None)


def _geometry(row, area):
    rect = [row.get(key) for key in ("x", "y", "width", "height")]
    ax, ay, aw, ah = area
    if (any(type(v) is not int for v in rect) or rect[2] < 100 or rect[3] < 100
            or rect[0] < ax or rect[1] < ay
            or rect[0] + rect[2] > ax + aw or rect[1] + rect[3] > ay + ah):
        return None
    return [rect[0] - ax, rect[1] - ay, rect[2], rect[3]]


def save_desktop_profile(db_path, name, windows, approve):
    """Captura estado real de até quatro janelas, sem abrir nem movê-las."""
    name = _name(name)
    selectors = _selectors(windows)
    if db_path is None:
        return {"status": "unavailable", "reason": "Banco de perfis não configurado"}
    rows, monitors, spaces = _inventory(), _monitors(), _workspaces()
    if rows is None or monitors is None or spaces is None:
        return {"status": "unavailable", "install_url": EXTENSION_URL}
    entries, selected = [], []
    valid_spaces = {item["index"] for item in spaces}
    for selector in selectors:
        row, error = _select(rows, selector["app"], selector["title"])
        if error:
            return {"status": error, "selector": selector}
        monitor = _monitor_for(row, monitors)
        workspace = row.get("workspace_index")
        if monitor is None or type(workspace) is not int or workspace not in valid_spaces:
            return {"status": "unavailable", "reason": "Monitor ou área da janela desconhecido"}
        area = _workarea(monitor["index"])
        rect = _geometry(row, area) if area is not None else None
        if rect is None:
            return {"status": "unavailable", "reason": "Geometria fora da área útil"}
        selected.append(row)
        entries.append({**selector, "monitor_index": monitor["index"],
                        "connector": monitor["connector"],
                        "monitor_count": len(monitors), "workspace_index": workspace,
                        "workarea": [area[2], area[3]], "rect": rect})
    if len({row["id"] for row in selected}) != len(selected):
        return {"status": "ambiguous", "reason": "Seletores repetem a mesma janela"}
    active = next(item["index"] for item in spaces if item["is_active"])
    if not approve(f"SALVAR PERFIL DE AMBIENTE '{name}' com {len(entries)} janelas?"):
        return {"status": "rejected"}
    current, current_monitors, current_spaces = _inventory(), _monitors(), _workspaces()
    if (current is None or current_monitors != monitors or current_spaces != spaces):
        return {"status": "changed", "reason": "Desktop mudou durante a autorização"}
    for old, entry in zip(selected, entries):
        now, error = _select(current, entry["app"], entry["title"])
        area = _workarea(entry["monitor_index"])
        if (error or not _identity_ok(old, now)
                or now.get("monitor") != entry["monitor_index"]
                or now.get("workspace_index") != entry["workspace_index"]
                or area is None or [area[2], area[3]] != entry["workarea"]
                or _geometry(now, area) != entry["rect"]):
            return {"status": "changed", "reason": "Janela mudou durante a autorização"}
    connection = _connection(db_path)
    try:
        payload = json.dumps({"version": 1, "active_workspace": active,
                              "windows": entries}, ensure_ascii=False)
        connection.execute("INSERT INTO desktop_profiles(name,payload) VALUES (?,?) "
                           "ON CONFLICT(name) DO UPDATE SET payload=excluded.payload, "
                           "updated_at=CURRENT_TIMESTAMP", (name, payload))
        connection.execute("DELETE FROM desktop_profile_launches WHERE profile_name=?", (name,))
        connection.commit()
    finally:
        connection.close()
    return {"status": "saved", "name": name, "windows": len(entries)}


def list_desktop_profiles(db_path):
    connection = _connection(db_path)
    if connection is None:
        return {"status": "unavailable", "reason": "Banco de perfis não configurado"}
    try:
        rows = connection.execute("SELECT name,updated_at FROM desktop_profiles "
                                  "ORDER BY name LIMIT 100").fetchall()
    finally:
        connection.close()
    return {"status": "listed", "profiles": [
        {"name": name, "updated_at": updated_at} for name, updated_at in rows]}


def _load(db_path, name):
    connection = _connection(db_path)
    if connection is None:
        return None
    try:
        row = connection.execute("SELECT payload FROM desktop_profiles WHERE name=?",
                                 (name,)).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    try:
        profile = json.loads(row[0])
        entries = profile["windows"]
        if profile.get("version") != 1 or not 1 <= len(entries) <= 4:
            raise ValueError
        if not all(isinstance(entry, dict) for entry in entries):
            raise ValueError
        selectors = _selectors([
            {key: entry.get(key) for key in ("app", "title", "app_id")}
            for entry in entries])
        if type(profile["active_workspace"]) is not int:
            raise ValueError
        for entry, selector in zip(entries, selectors):
            if (not isinstance(entry, dict) or set(entry) != set(selector) | {
                    "monitor_index", "connector", "monitor_count", "workspace_index",
                    "workarea", "rect"}
                    or type(entry["monitor_index"]) is not int
                    or type(entry["workspace_index"]) is not int
                    or type(entry["monitor_count"]) is not int
                    or not isinstance(entry["connector"], str)
                    or len(entry["connector"]) > 100):
                raise ValueError
            _scaled_rect((0, 0, *entry["workarea"]), entry["workarea"], entry["rect"])
        return profile
    except (ValueError, TypeError, KeyError, IndexError, AttributeError,
            OverflowError) as exc:
        raise ValueError("Perfil de ambiente salvo inválido") from exc


def _target_monitor(entry, monitors):
    connector = entry["connector"]
    if connector:
        matching = [m for m in monitors if m["connector"] == connector]
    elif entry["monitor_count"] == len(monitors) == 1:
        matching = monitors
    else:
        matching = []
    return matching[0] if len(matching) == 1 else None


def _wait_window(app, title, retries=8, delay=0.25):
    for attempt in range(retries):
        if attempt:
            time.sleep(delay)
        rows = _inventory()
        if rows is None:
            continue
        chosen, error = _select(rows, app, title)
        if chosen is not None or error == "ambiguous":
            return chosen, error
    return None, "not_observed"


def restore_desktop_profile(db_path, name, approve):
    """Restaura passo a passo e informa resultado parcial sem repetir launches."""
    name = _name(name)
    if db_path is None:
        return {"status": "unavailable", "reason": "Banco de perfis não configurado"}
    profile = _load(db_path, name)
    if profile is None:
        return {"status": "not_found", "name": name}
    monitors, spaces, rows = _monitors(), _workspaces(), _inventory()
    if monitors is None or spaces is None or rows is None:
        return {"status": "unavailable", "install_url": EXTENSION_URL}
    targets = []
    space_indices = {s["index"] for s in spaces}
    if profile["active_workspace"] not in space_indices:
        return {"status": "not_found", "reason": "Área ativa salva não existe"}
    selected_ids = set()
    for entry_index, entry in enumerate(profile["windows"]):
        monitor = _target_monitor(entry, monitors)
        if monitor is None or entry["workspace_index"] not in space_indices:
            return {"status": "not_found", "reason": "Monitor ou área salva indisponível"}
        area = _workarea(monitor["index"])
        if area is None:
            return {"status": "unavailable", "reason": "Área útil indisponível"}
        try:
            rect = _scaled_rect(area, entry["workarea"], entry["rect"])
        except (ValueError, TypeError, OverflowError):
            return {"status": "unavailable", "reason": "Geometria salva incompatível"}
        chosen, error = _select(rows, entry["app"], entry["title"])
        if error == "ambiguous" or (chosen is not None and chosen["id"] in selected_ids):
            return {"status": "ambiguous", "reason": "Janela do perfil não é única"}
        if chosen is None and entry["app_id"] is None:
            return {"status": "not_observed", "reason": "Janela ausente sem app_id para abrir"}
        if chosen is None and _pending(db_path, name, entry_index):
            return {"status": "launch_uncertain", "reason":
                    "Abertura anterior não foi confirmada; verifique o aplicativo antes de repetir"}
        if chosen is not None:
            selected_ids.add(chosen["id"])
            if _pending(db_path, name, entry_index):
                _set_pending(db_path, name, entry_index, False)
        targets.append((entry_index, entry, monitor, area, rect, chosen))
    if not approve(f"RESTAURAR AMBIENTE '{name}' com {len(targets)} janelas? "
                   "Aplicativos ausentes com app_id serão abertos."):
        return {"status": "rejected"}
    outcomes = []
    for entry_index, entry, monitor, area, rect, observed_before in targets:
        outcome = {"app": entry["app"], "steps": []}
        outcomes.append(outcome)
        current_monitors = _monitors()
        current_target = (_target_monitor(entry, current_monitors)
                          if current_monitors is not None else None)
        if (current_target is None or current_target["index"] != monitor["index"]
                or _workarea(monitor["index"]) != area):
            outcome["steps"].append({"action": "topology", "status": "changed"})
            break
        rows = _inventory()
        if rows is None:
            outcome["steps"].append({"action": "observe", "status": "unavailable"})
            break
        chosen, error = _select(rows, entry["app"], entry["title"])
        if error == "ambiguous":
            outcome["steps"].append({"action": "select", "status": "ambiguous"})
            break
        if observed_before is not None and (
                chosen is None or not _identity_ok(observed_before, chosen)):
            outcome["steps"].append({"action": "select", "status": "changed"})
            break
        if chosen is None:
            if entry["app_id"] is None:
                outcome["steps"].append({"action": "select", "status": "not_observed"})
                break
            try:
                launched = launch_installed_app(entry["app_id"], approve)
            except (OSError, ValueError) as exc:
                outcome["steps"].append({"action": "launch", "status": "failed",
                                         "reason": str(exc)[:160]})
                break
            outcome["steps"].append({"action": "launch", "status": launched.get("status")})
            if launched.get("status") != "launched_unverified":
                break
            _set_pending(db_path, name, entry_index, True)
            chosen, error = _wait_window(entry["app"], entry["title"])
            if error:
                outcome["steps"].append({"action": "observe", "status": error})
                break
            _set_pending(db_path, name, entry_index, False)
        app, title = entry["app"], entry["title"]
        monitor_number = monitor["index"] + 1
        if chosen.get("monitor") != monitor["index"]:
            moved = move_window_to_monitor(app, approve, monitor_number, title)
            outcome["steps"].append({"action": "monitor", "status": moved["status"]})
            if moved["status"] != "window_monitor_verified":
                break
        if chosen.get("workspace_index") != entry["workspace_index"]:
            moved = move_window_to_workspace(app, entry["workspace_index"] + 1,
                                             approve, title)
            outcome["steps"].append({"action": "workspace", "status": moved["status"]})
            if moved["status"] not in ("window_workspace_verified", "already_in_state"):
                break
        rows = _inventory()
        current, error = _select(rows, app, title) if rows is not None else (None, "unavailable")
        if error:
            outcome["steps"].append({"action": "geometry", "status": error})
            break
        actual = [current.get(key) for key in ("x", "y", "width", "height")]
        if actual == list(rect):
            outcome["steps"].append({"action": "geometry", "status": "already_in_state"})
        else:
            if _workarea(monitor["index"]) != area:
                outcome["steps"].append({"action": "geometry", "status": "changed"})
                break
            placed = place_window(app, "custom", approve, title=title,
                                  x_px=rect[0] - area[0], y_px=rect[1] - area[1],
                                  width_px=rect[2], height_px=rect[3])
            outcome["steps"].append({"action": "geometry", "status": placed["status"]})
            if placed["status"] != "geometry_verified":
                break
        final_rows = _inventory()
        final, error = (_select(final_rows, app, title)
                        if final_rows is not None else (None, "unavailable"))
        geometry = [final.get(key) for key in ("x", "y", "width", "height")] if final else []
        verified = (error is None and _identity_ok(chosen, final)
                    and final.get("monitor") == monitor["index"]
                    and final.get("workspace_index") == entry["workspace_index"]
                    and len(geometry) == 4
                    and all(type(value) is int and abs(value - expected) <= 48
                            for value, expected in zip(geometry, rect)))
        outcome["steps"].append({"action": "verify", "status":
                                 "state_verified" if verified else "state_unverified"})
        if not verified:
            break
    else:
        current_spaces = _workspaces()
        if current_spaces is None:
            return {"status": "profile_partial", "name": name, "outcomes": outcomes}
        active = next(s["index"] for s in current_spaces if s["is_active"])
        if active != profile["active_workspace"]:
            switched = activate_workspace(profile["active_workspace"] + 1, approve)
            outcomes.append({"app": "", "steps": [{"action": "active_workspace",
                                                    "status": switched["status"]}]})
            if switched["status"] not in ("workspace_verified", "already_in_state"):
                return {"status": "profile_partial", "name": name, "outcomes": outcomes}
        return {"status": "profile_verified", "name": name, "outcomes": outcomes}
    return {"status": "profile_partial", "name": name, "outcomes": outcomes}
