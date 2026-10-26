import unittest
from jarvis.router import route, tool_catalog


class RoutingRegressions(unittest.TestCase):
    def test_indirect_actions_keep_tools(self):
        for text in ('Pode iniciar o Spotify?', 'Você pode instalar o VLC?',
                     'Consegue adicionar uma tarefa?', 'Pode tocar música?'):
            with self.subTest(text=text):
                self.assertEqual(route(text), 'tools')

    def test_compound_requests_preserve_all_capabilities(self):
        specs = [{'name': name} for name in ('save_desktop_profile', 'launch_installed_app',
                 'move_window_to_monitor', 'focus_window', 'desktop_windows')]
        for text in ('Salve o ambiente e abra o Firefox',
                     'Mova o Firefox para o segundo monitor e abra o terminal',
                     'Traga o Firefox para frente; abra o terminal',
                     'Liste os layouts e depois abra o editor'):
            with self.subTest(text=text):
                self.assertEqual(tool_catalog(text, specs), specs)
