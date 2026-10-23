"""Navegação e indicador vetorial, independentes do backend da IA."""
import math
import tkinter as tk
from tkinter import ttk
from .gui_theme import BG, PANEL, BORDER, ACCENT, TEXT, MUTED


class ScrollPanel(ttk.Frame):
    """Área recolhida de configurações com viewport e foco acessível."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=BG, width=320)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = ttk.Frame(self.canvas, padding=8)
        self._item = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(self._item, width=event.width))
        self._top = self.winfo_toplevel()
        self._focus_binding = self._top.bind('<FocusIn>', self._reveal, add='+')
        self._wheel_binding = self._top.bind('<MouseWheel>', self._wheel, add='+')
        self.bind('<Destroy>', self._cleanup)

    def _contains(self, widget):
        while widget is not None:
            if widget is self.content:
                return True
            widget = getattr(widget, 'master', None)
        return False

    def _reveal(self, event):
        if not self._contains(event.widget):
            return
        y = event.widget.winfo_rooty() - self.content.winfo_rooty()
        visible_top = self.canvas.canvasy(0)
        visible_bottom = visible_top + self.canvas.winfo_height()
        height = max(1, self.content.winfo_height())
        if y < visible_top:
            self.canvas.yview_moveto(y / height)
        elif y + event.widget.winfo_height() > visible_bottom:
            self.canvas.yview_moveto((y + event.widget.winfo_height() - self.canvas.winfo_height()) / height)

    def _wheel(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        if self._contains(widget):
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')

    def _cleanup(self, event):
        if event.widget is self:
            self._top.unbind('<FocusIn>', self._focus_binding)
            self._top.unbind('<MouseWheel>', self._wheel_binding)


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
