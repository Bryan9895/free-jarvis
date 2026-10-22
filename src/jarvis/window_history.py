"""Histórico local e limitado de operações sobre janelas.

Não registra títulos de janelas, texto de arquivos nem argumentos arbitrários.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

WINDOW_MUTATIONS = {
    "focus_window", "manage_window", "close_window", "place_window",
    "arrange_windows", "arrange_window_grid", "save_window_layout",
    "restore_window_layout",
    "activate_workspace", "move_window_to_workspace", "move_window_to_monitor",
}


def _connection(db_path):
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE IF NOT EXISTS window_action_history ("
                       "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "tool TEXT NOT NULL, status TEXT NOT NULL, "
                       "details TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    return connection


def record_window_action(db_path, tool, arguments, outcome):
    if db_path is None or tool not in WINDOW_MUTATIONS:
        return None
    details = {}
    if isinstance(arguments, dict):
        for key in ("app", "left_app", "right_app", "position", "action", "name"):
            value = arguments.get(key)
            if isinstance(value, str):
                details[key] = value[:100]
        windows = arguments.get("windows")
        if isinstance(windows, list):
            details["window_count"] = min(len(windows), 4)
        workspace_number = arguments.get("workspace_number")
        if type(workspace_number) is int and 1 <= workspace_number <= 64:
            details["workspace_number"] = workspace_number
        monitor_number = arguments.get("monitor_number")
        if type(monitor_number) is int and 1 <= monitor_number <= 65:
            details["monitor_number"] = monitor_number
    result = outcome.get("result") if isinstance(outcome, dict) else None
    status = result.get("status") if isinstance(result, dict) else None
    if not isinstance(status, str):
        status = "failed" if isinstance(outcome, dict) and outcome.get("error") else "unverified"
    geometry = result.get("geometry") if isinstance(result, dict) else None
    if (isinstance(geometry, (list, tuple)) and len(geometry) == 4
            and all(type(value) is int for value in geometry)):
        details["geometry"] = list(geometry)
    connection = _connection(db_path)
    try:
        cursor = connection.execute(
            "INSERT INTO window_action_history(tool,status,details) VALUES (?,?,?)",
            (tool, status[:60], json.dumps(details, ensure_ascii=False)))
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def window_action_history(db_path, limit=20):
    if db_path is None:
        return {"status": "unavailable", "reason": "Banco de histórico não configurado"}
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Limite do histórico deve ser inteiro entre 1 e 50")
    connection = _connection(db_path)
    try:
        rows = connection.execute(
            "SELECT id,tool,status,details,created_at FROM window_action_history "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        connection.close()
    return {"status": "listed", "actions": [
        {"id": ident, "tool": tool, "status": status, "details": json.loads(details),
         "created_at": created_at}
        for ident, tool, status, details, created_at in rows]}
