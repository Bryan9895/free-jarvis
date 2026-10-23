"""Migração de bancos legados preserva registros sem recriar tabelas."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from jarvis.database import SCHEMA_VERSION, connect_database
from jarvis.memory import Memory
from jarvis.plan_store import PlanStore
from jarvis.agent import Agent
from jarvis.tools import Toolkit


class DatabaseMigrationTests(unittest.TestCase):
    def test_legacy_rows_survive_migration_and_reopen(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.sqlite3"
            old = sqlite3.connect(path)
            old.execute("CREATE TABLE turns (id INTEGER PRIMARY KEY, role TEXT NOT NULL, "
                        "content TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            old.execute("INSERT INTO turns(role,content) VALUES ('user','mensagem antiga')")
            old.execute("CREATE TABLE task_plans (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "payload TEXT NOT NULL, status TEXT NOT NULL, "
                        "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            old.execute("INSERT INTO task_plans(payload,status) VALUES "
                        "('{\"goal\":\"antigo\",\"status\":\"ready\"}','ready')")
            old.commit()
            old.close()
            memory = Memory(path)
            plans = PlanStore(path)
            self.assertEqual(memory.recent()[0]["content"], "mensagem antiga")
            self.assertEqual(plans.latest()["goal"], "antigo")
            self.assertEqual(memory.conn.execute("PRAGMA user_version").fetchone()[0],
                             SCHEMA_VERSION)
            self.assertIsNotNone(memory.conn.execute(
                "SELECT name FROM sqlite_master WHERE name='execution_events'").fetchone())
            plans.close()
            memory.close()

    def test_future_schema_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "future.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA user_version=99")
            connection.close()
            with self.assertRaisesRegex(RuntimeError, "mais nova"):
                connect_database(path)
            connection = sqlite3.connect(path)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 99)
            connection.close()

    def test_execution_events_store_states_without_arguments(self):
        class Client:
            def __init__(self):
                self.calls = 0

            def responses(self, _payload):
                self.calls += 1
                if self.calls == 1:
                    return {"output": [{"type": "function_call", "name": "write_file",
                        "call_id": "one", "arguments":
                        '{"path":"secret.txt","content":"very-secret-value"}'}]}
                return {"output_text": "ok", "output": []}

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data.sqlite3"
            memory = Memory(path)
            toolkit = Toolkit(Path(temp) / "work", approve=lambda _: True, layout_db=path)
            agent = Agent(Client(), toolkit, memory, "fake")
            agent.ask("Escreva um arquivo", task_id="task-1", step_id=3)
            row = memory.conn.execute("SELECT task_id,step_id,tool,state,raw_status "
                                      "FROM execution_events").fetchone()
            self.assertEqual(row, ("task-1", 3, "write_file", "verified", "written"))
            self.assertNotIn("very-secret-value", str(row))
            self.assertEqual(agent.last_metrics["task_id"], "task-1")
            toolkit.close()
            memory.close()


if __name__ == "__main__":
    unittest.main()
