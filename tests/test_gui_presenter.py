import unittest
from jarvis.gui_presenter import plan_progress, plan_details, action_summary, status_label


class PresenterTests(unittest.TestCase):
    def test_unverified_steps_do_not_inflate_progress(self):
        plan = {'steps':[{'id':1,'status':'verified'}, {'id':2,'status':'reported_unverified'}]}
        self.assertEqual(plan_progress(plan), (1,2))
        self.assertIn('não verificado', plan_details(plan))

    def test_unknown_status_does_not_become_success(self):
        self.assertEqual(status_label('custom'), 'Estado informado: custom')
        self.assertIn('Alvo não encontrado', action_summary({'status':'not_found','tab_id':4}))
        self.assertIn('#4', action_summary({'status':'not_found','tab_id':4}))
