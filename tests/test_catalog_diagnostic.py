import unittest
from unittest.mock import Mock
from jarvis.catalog_diagnostic import inspect_catalog
from jarvis.fcc import FCCError


class CatalogDiagnosticTests(unittest.TestCase):
    def client(self):
        client = Mock(base_url='http://127.0.0.1:8082')
        client.models.return_value = {'data': [
            {'id': 'claude-3-freecc-no-thinking/openai/model', 'provider_model_ref':'openai/model'},
            {'id':'ollama/local'}], 'default_model_id':'ollama/local'}
        return client

    def test_aliases_do_not_count_as_missing_models(self):
        client = self.client()
        client.request.side_effect = [ {'data':[{'id':'claude-sonnet'}]},
                                      {'models':['openai/model','ollama/local','gemini/extra']} ]
        report = inspect_catalog(client)
        self.assertEqual(report['responses_count'], 2)
        self.assertEqual(report['admin']['missing_in_responses'], ['gemini/extra'])
        self.assertEqual(report['by_provider'], {'ollama':1,'openai':1})
        self.assertTrue(all(call.args[0] == 'GET' for call in client.request.call_args_list))
        client.responses.assert_not_called()

    def test_forbidden_admin_does_not_break_public_catalog(self):
        client = self.client()
        client.request.side_effect = [ {'data':[]}, FCCError('forbidden',403) ]
        report = inspect_catalog(client)
        self.assertEqual(report['responses_count'], 2)
        self.assertFalse(report['admin']['available'])
        self.assertEqual(report['admin']['http_status'],403)

    def test_invalid_responses_is_reported(self):
        client = self.client()
        client.models.return_value = {'data':None}
        with self.assertRaises(FCCError):
            inspect_catalog(client)

    def test_server_pagination_is_not_silently_ignored(self):
        client = self.client()
        client.models.return_value['has_more'] = True
        client.request.side_effect = [ {'data':[]}, {'models':[]} ]
        self.assertTrue(inspect_catalog(client)['has_more'])
