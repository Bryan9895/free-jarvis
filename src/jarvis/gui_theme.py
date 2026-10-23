"""Identidade visual desktop do Jarvis; sem assets ou código externos."""
from tkinter import ttk

BG = '#080f19'
PANEL = '#101c2b'
SURFACE = '#16263a'
BORDER = '#294058'
ACCENT = '#53d6e8'
TEXT = '#e7f0f7'
MUTED = '#9aaec2'


def apply_theme(root):
    root.configure(background=BG)
    root.option_add('*Font', ('DejaVu Sans', 10))
    root.option_add('*Listbox.background', PANEL)
    root.option_add('*Listbox.foreground', TEXT)
    root.option_add('*Listbox.selectBackground', BORDER)
    root.option_add('*Text.background', PANEL)
    root.option_add('*Text.foreground', TEXT)
    root.option_add('*Text.insertBackground', ACCENT)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=BG, foreground=TEXT, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, troughcolor=PANEL)
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG, foreground=TEXT)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Brand.TLabel', foreground=ACCENT, font=('DejaVu Sans', 19, 'bold'))
    style.configure('TButton', background=SURFACE, foreground=TEXT, padding=(10, 7))
    style.map('TButton', background=[('active', BORDER), ('pressed', BORDER)],
              foreground=[('disabled', MUTED)])
    style.configure('Nav.TButton', anchor='w', padding=(12, 9), borderwidth=0)
    style.map('Nav.TButton', background=[('selected', SURFACE), ('active', BORDER)],
              foreground=[('selected', ACCENT)])
    style.configure('Accent.TButton', foreground=BG, background=ACCENT)
    style.map('Accent.TButton', background=[('active', '#87e5f1')])
    style.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, insertcolor=ACCENT, padding=7)
    style.configure('TCombobox', fieldbackground=PANEL, foreground=TEXT, arrowcolor=ACCENT, padding=5)
    style.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', TEXT)])
    style.configure('TNotebook', background=BG, borderwidth=0)
    style.configure('TNotebook.Tab', background=SURFACE, foreground=MUTED, padding=(10, 7))
    style.map('TNotebook.Tab', background=[('selected', PANEL), ('active', BORDER)],
              foreground=[('selected', ACCENT), ('active', TEXT)])
    style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=29, borderwidth=0)
    style.map('Treeview', background=[('selected', BORDER)], foreground=[('selected', TEXT)])
    style.configure('Treeview.Heading', background=SURFACE, foreground=ACCENT, padding=7)
    return style
