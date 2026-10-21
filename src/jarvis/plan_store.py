"""Histórico local de planos e estados em SQLite."""
import json
import sqlite3
from pathlib import Path


class PlanStore:
    def __init__(self, path):
        db = Path(path).expanduser()
        db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS task_plans ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "payload TEXT NOT NULL, status TEXT NOT NULL, "
            "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self.conn.commit()

    def save(self, plan):
        serialized = json.dumps(plan, ensure_ascii=False)
        if plan.get("id") is None:
            cursor = self.conn.execute(
                "INSERT INTO task_plans (payload, status) VALUES (?,?)",
                (serialized, plan["status"]),
            )
            plan["id"] = cursor.lastrowid
            serialized = json.dumps(plan, ensure_ascii=False)
            self.conn.execute(
                "UPDATE task_plans SET payload=? WHERE id=?",
                (serialized, plan["id"]),
            )
        else:
            self.conn.execute(
                "UPDATE task_plans SET payload=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (serialized, plan["status"], plan["id"]),
            )
        self.conn.commit()
        return plan["id"]

    def latest(self):
        row = self.conn.execute(
            "SELECT payload FROM task_plans ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return json.loads(row[0]) if row else None

    def recent(self, limit=10):
        limit = max(1, min(30, int(limit)))
        rows = self.conn.execute(
            "SELECT payload FROM task_plans ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def close(self):
        self.conn.close()
