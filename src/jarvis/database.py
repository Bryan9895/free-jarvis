"""Migrações SQLite não destrutivas para o banco local da JARVIS."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

_BASE_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS turns (id INTEGER PRIMARY KEY, role TEXT NOT NULL, "
    "content TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS task_plans (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "payload TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS window_layout_profiles (name TEXT PRIMARY KEY, "
    "payload TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS desktop_profiles (name TEXT PRIMARY KEY, "
    "payload TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS desktop_profile_launches (profile_name TEXT NOT NULL, "
    "entry_index INTEGER NOT NULL, PRIMARY KEY(profile_name, entry_index))",
    "CREATE TABLE IF NOT EXISTS window_action_history (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "tool TEXT NOT NULL, status TEXT NOT NULL, details TEXT NOT NULL, "
    "created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
)

_EVENT_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS execution_events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "task_id TEXT NOT NULL, step_id INTEGER, tool TEXT NOT NULL, "
    "state TEXT NOT NULL, raw_status TEXT NOT NULL, duration_ms REAL, "
    "created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
    "CREATE INDEX IF NOT EXISTS execution_events_task ON execution_events(task_id, id)",
)


def migrate(connection: sqlite3.Connection) -> int:
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("Banco criado por versão mais nova da JARVIS")
        if version < 1:
            for statement in _BASE_SCHEMA:
                connection.execute(statement)
            connection.execute("PRAGMA user_version=1")
        if version < 2:
            for statement in _EVENT_SCHEMA:
                connection.execute(statement)
            connection.execute("PRAGMA user_version=2")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return SCHEMA_VERSION


def connect_database(path) -> sqlite3.Connection:
    location = Path(path).expanduser()
    location.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(location)
    try:
        migrate(connection)
    except Exception:
        connection.close()
        raise
    return connection


def record_execution_event(path, task_id: str, step_id: int | None, tool: str,
                           state: str, raw_status: str, duration_ms: float | None):
    """Persiste somente identificadores/estados; nunca argumentos ou conteúdo."""
    connection = connect_database(path)
    try:
        cursor = connection.execute(
            "INSERT INTO execution_events(task_id,step_id,tool,state,raw_status,duration_ms) "
            "VALUES (?,?,?,?,?,?)",
            (task_id, step_id, tool, state, raw_status, duration_ms))
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()
