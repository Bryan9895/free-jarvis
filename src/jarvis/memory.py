"""Memória conversacional local de sessão, sem gravação de segredos intencional."""
import sqlite3
from pathlib import Path
from .database import connect_database

class Memory:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = connect_database(path)

    def add(self, role: str, content: str):
        self.conn.execute("INSERT INTO turns(role,content) VALUES (?,?)", (role, content))
        self.conn.commit()

    def recent(self, limit=10):
        rows = self.conn.execute("SELECT role,content FROM turns ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"role": r, "content": c} for r,c in reversed(rows)]

    def close(self):
        self.conn.close()
