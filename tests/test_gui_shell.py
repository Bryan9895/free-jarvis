"""Integração de navegação/HUD quando há display de teste disponível."""
import os
import unittest
import tkinter as tk
from tkinter import ttk
from jarvis.gui_shell import WorkspacePanels, AssistantHud
from jarvis.gui_theme import apply_theme


@unittest.skipUnless(os.getenv('DISPLAY'), 'Display gráfico indisponível')
class GuiShellTests(unittest.TestCase):
    def test_navigation_hud_and_timer_cleanup(self):
        root = tk.Tk()
        try:
            apply_theme(root)
            nav = ttk.Frame(root)
            nav.pack(side='left')
            workspace = WorkspacePanels(root, nav)
            workspace.pack(fill='both', expand=True)
            workspace.add(ttk.Frame(workspace), text='Tarefas')
            workspace.add(ttk.Frame(workspace), text='Voz')
            workspace.buttons[1].invoke()
            self.assertEqual(workspace.selected, 1)
            hud = AssistantHud(root)
            hud.pack()
            hud.set_state('ESCUTANDO', 'Diga Jarvis', active=True)
            root.update()
            self.assertIsNotNone(hud._timer)
            hud.set_state('PRONTO')
            self.assertIsNone(hud._timer)
            hud.destroy()
        finally:
            root.destroy()
