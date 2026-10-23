"""Histórico local de planos e estados em SQLite."""
import json
import sqlite3
from pathlib import Path
from .database import connect_database


class PlanStore:
    def __init__(self, path):
        self.conn = connect_database(path)

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

    def get(self, plan_id):
        if type(plan_id) is not int or plan_id < 1:
            raise ValueError("Identificador de plano inválido.")
        row = self.conn.execute(
            "SELECT payload FROM task_plans WHERE id=?", (plan_id,)
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
