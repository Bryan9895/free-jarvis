"""Lista pessoal persistente; marcar concluída não executa um plano."""
from .database import connect_database


class TaskBoard:
    def __init__(self, path):
        if path is None:
            raise ValueError('Banco de tarefas não configurado')
        self.path = path

    def list(self, status=None):
        if status not in (None, 'pending', 'in_progress', 'done'):
            raise ValueError('Estado de tarefa inválido')
        connection = connect_database(self.path)
        try:
            rows = connection.execute(
                'SELECT id,title,status,priority FROM personal_tasks ' +
                ('WHERE status=? ' if status else '') + 'ORDER BY priority DESC,id',
                (status,) if status else ()).fetchall()
            return {'status': 'listed', 'tasks': [dict(zip(
                ('id','title','state','priority'), row)) for row in rows]}
        finally:
            connection.close()

    def add(self, title, priority=2):
        if not isinstance(title, str) or not title.strip() or len(title) > 500:
            raise ValueError('Título deve conter de 1 a 500 caracteres')
        if type(priority) is not int or priority not in (1, 2, 3):
            raise ValueError('Prioridade deve ser 1, 2 ou 3')
        connection = connect_database(self.path)
        try:
            with connection:
                cursor = connection.execute(
                    'INSERT INTO personal_tasks(title,status,priority) VALUES (?, ?, ?)',
                    (title.strip(), 'pending', priority))
                task_id = cursor.lastrowid
            return {'status': 'state_verified', 'task_id': task_id, 'state': 'pending'}
        finally:
            connection.close()

    def update(self, task_id, status):
        if type(task_id) is not int or task_id < 1:
            raise ValueError('ID de tarefa inválido')
        if status not in ('pending', 'in_progress', 'done'):
            raise ValueError('Estado de tarefa inválido')
        connection = connect_database(self.path)
        try:
            with connection:
                cursor = connection.execute(
                    'UPDATE personal_tasks SET status=? WHERE id=?', (status, task_id))
            return {'status': 'state_verified' if cursor.rowcount else 'not_found',
                    'task_id': task_id, 'state': status}
        finally:
            connection.close()
