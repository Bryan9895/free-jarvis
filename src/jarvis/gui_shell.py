"""Navegação e indicador vetorial, independentes do backend da IA."""
import math
import tkinter as tk
from tkinter import ttk
from .gui_theme import BG, PANEL, BORDER, ACCENT, TEXT, MUTED


class WorkspacePanels(ttk.Frame):
    def __init__(self, parent, navigation):
        super().__init__(parent)
        self.navigation = navigation
        self.panels = []
        self.buttons = []
        self.selected = None
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def add(self, panel, *, text):
        index = len(self.panels)
        self.panels.append(panel)
        panel.grid(row=0, column=0, sticky='nsew')
        button = ttk.Button(self.navigation, text=text, style='Nav.TButton',
                            command=lambda: self.select(index))
        button.pack(fill='x', pady=1)
        self.buttons.append(button)
        self.select(index if self.selected is None else self.selected)

    def select(self, index):
        self.selected = index
        for number, panel in enumerate(self.panels):
            if number == index:
                panel.grid(row=0, column=0, sticky='nsew')
                panel.tkraise()
            else:
                panel.grid_remove()
        for number, button in enumerate(self.buttons):
            button.state(['selected'] if number == index else ['!selected'])


class AssistantHud(tk.Canvas):
    """Animação de estado; não representa intensidade de áudio nem métricas."""
    def __init__(self, parent):
        super().__init__(parent, height=145, background=BG, highlightthickness=0)
        self.label = 'CONECTANDO'
        self.detail = 'Preparando seu assistente'
        self.active = False
        self.phase = 0
        self._timer = None
        self.bind('<Configure>', lambda _: self._draw())
        self.bind('<Destroy>', self._destroy)

    def set_state(self, label, detail='', active=False):
        self.label, self.detail, self.active = label, detail, active
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None
        self._draw()
        if active:
            self._timer = self.after(100, self._tick)

    def _tick(self):
        self._timer = None
        self.phase += 0.16
        self._draw()
        if self.active:
            self._timer = self.after(100, self._tick)

    def _draw(self):
        self.delete('all')
        x, y = 76, 72
        for radius in (49, 38, 27):
            self.create_oval(x-radius, y-radius, x+radius, y+radius,
                             outline=BORDER, width=1)
        start = (self.phase * 30) % 360
        self.create_arc(x-49, y-49, x+49, y+49, start=start, extent=100,
                        style='arc', outline=ACCENT, width=3)
        pulse = 12 + (math.sin(self.phase) * 2 if self.active else 0)
        self.create_oval(x-pulse, y-pulse, x+pulse, y+pulse, fill=ACCENT, outline='')
        self.create_text(150, 54, text='J A R V I S', anchor='w', fill=TEXT,
                         font=('DejaVu Sans', 20, 'bold'))
        self.create_text(150, 84, text=self.label, anchor='w', fill=ACCENT,
                         font=('DejaVu Sans', 10, 'bold'))
        self.create_text(150, 108, text=self.detail, anchor='w', fill=MUTED,
                         width=max(180, self.winfo_width()-165), font=('DejaVu Sans', 9))

    def _destroy(self, event):
        if event.widget is self and self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None
