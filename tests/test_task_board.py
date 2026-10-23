import sqlite3
import tempfile
import unittest
from pathlib import Path
from jarvis.task_board import TaskBoard
from jarvis.tools import Toolkit
from jarvis.database import connect_database


class TaskBoardTests(unittest.TestCase):
    def test_order_state_and_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'tasks.db'
            board = TaskBoard(path)
            first = board.add('Estudar', 1)['task_id']
            high = board.add('Concluir Jarvis', 3)['task_id']
            self.assertEqual([t['id'] for t in TaskBoard(path).list()['tasks']], [high, first])
            self.assertEqual(board.update(high, 'done')['status'], 'state_verified')
            self.assertEqual(board.list('done')['tasks'][0]['title'], 'Concluir Jarvis')
            self.assertEqual(board.update(999, 'done')['status'], 'not_found')
            for title, priority in [('', 2), ('A', True), ('A', 4)]:
                with self.assertRaises(ValueError):
                    board.add(title, priority)

    def test_permissions_and_approval(self):
        with tempfile.TemporaryDirectory() as td:
            kit = Toolkit(Path(td), layout_db=Path(td)/'db',
                          approve=lambda _: False, enabled_capabilities={'tasks.read','tasks.write'})
            self.assertEqual(kit.execute('task_add', {'title':'A'})['result']['status'], 'rejected')
            self.assertEqual(kit.execute('task_list', {})['result']['tasks'], [])
            kit.close()
            kit = Toolkit(Path(td), layout_db=Path(td)/'db',
                          approve=lambda _: True, enabled_capabilities={'tasks.read'})
            self.assertIn('error', kit.execute('task_add', {'title':'A'}))
            kit.close()

    def test_migration_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'db'
            conn = connect_database(path)
            conn.execute("INSERT INTO turns(role,content) VALUES ('user','preservar')")
            conn.execute('DROP TABLE personal_tasks')
            conn.execute('PRAGMA user_version=2')
            conn.commit()
            conn.close()
            TaskBoard(path).add('Nova')
            conn = sqlite3.connect(path)
            self.assertEqual(conn.execute('SELECT content FROM turns').fetchone()[0], 'preservar')
            conn.close()
