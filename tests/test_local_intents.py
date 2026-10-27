import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock
from jarvis.agent import Agent
from jarvis.local_intents import task_add_intent
from jarvis.memory import Memory
from jarvis.tools import Toolkit


class LocalIntentTests(unittest.TestCase):
    def test_explicit_title_preserves_number_and_uses_existing_executor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory = Memory(root / 'memory.db')
            self.addCleanup(memory.close)
            toolkit = Toolkit(root, approve=lambda _: True, layout_db=root / 'memory.db')
            client = Mock()
            agent = Agent(client, toolkit, memory, 'fixture')
            answer = agent.ask('Adicione às tarefas: revisar relatório 3.')
            client.responses.assert_not_called()
            self.assertEqual(answer, 'Tarefa adicionada.')
            tasks = toolkit.task_list()['tasks']
            self.assertEqual(tasks[0]['title'], 'revisar relatório 3')
            self.assertEqual(tasks[0]['priority'], 2)
            self.assertEqual(agent.last_metrics['model_rounds'], 0)
            self.assertEqual(agent.last_metrics['tools_executed'], 1)
            self.assertEqual(len(memory.recent()), 2)

    def test_ambiguous_compound_priority_or_disabled_capability_stays_with_model(self):
        available = [{'name': 'task_add'}]
        for message in ('Adicione às tarefas: preparar relatório e crie o arquivo x.',
                        'Adicione às tarefas: relatório, prioridade 1.',
                        'Adicione revisar relatório às tarefas.',
                        'Adicione às tarefas: "título sem fechar'):
            self.assertIsNone(task_add_intent(message, available))
        self.assertIsNone(task_add_intent('Adicione às tarefas: relatório.', []))

    def test_denied_action_is_never_reported_as_added(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory = Memory(root / 'memory.db')
            self.addCleanup(memory.close)
            toolkit = Toolkit(root, approve=lambda _: False, layout_db=root / 'memory.db')
            answer = Agent(Mock(), toolkit, memory, 'fixture').ask('Adicione às tarefas: relatório.')
            self.assertIn('Não foi possível', answer)
            self.assertEqual(toolkit.task_list()['tasks'], [])
