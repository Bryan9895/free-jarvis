"""Memória conversacional local de sessão, sem gravação de segredos intencional."""
import sqlite3
from pathlib import Path

class Memory:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS turns (id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        self.conn.commit()

    def add(self, role: str, content: str):
        self.conn.execute("INSERT INTO turns(role,content) VALUES (?,?)", (role, content))
        self.conn.commit()

    def recent(self, limit=10):
        rows = self.conn.execute("SELECT role,content FROM turns ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"role": r, "content": c} for r,c in reversed(rows)]

    def close(self):
        self.conn.close()
