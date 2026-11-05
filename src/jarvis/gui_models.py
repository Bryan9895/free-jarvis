"""Seleção explícita do modelo de conversa, separada do Whisper local."""
import tkinter as tk
from tkinter import ttk, scrolledtext


def build_models_panel(window, tabs):
    panel = ttk.Frame(tabs, padding=8)
    tabs.add(panel, text='Modelos')
    ttk.Label(panel, text='Modelo de conversa', font=('DejaVu Sans', 14, 'bold')).pack(anchor='w')
    profile = getattr(getattr(window.backend, 'config', None), 'profile', 'fcc')
    label = 'Local · OpenJarvis/Ollama' if profile == 'local' else 'Engenharia FCC'
    window.profile_label = tk.StringVar(value=label)
    window.profile_choice = tk.StringVar(value=profile if profile in ('local', 'fcc') else 'fcc')
    ttk.Label(panel, textvariable=window.profile_label).pack(anchor='w')
    ttk.Combobox(panel, textvariable=window.profile_choice, values=('local', 'fcc'), state='readonly').pack(fill='x')
    ttk.Button(panel, text='Aplicar perfil e modelo informado', command=lambda: window.backend.submit(
        'select_profile', {'profile': window.profile_choice.get(), 'model': window.model_choice.get()})).pack(fill='x', pady=4)
    ttk.Label(panel, text='Local usa pesos instalados. Engenharia FCC usa o catálogo configurado. Whisper transforma sua fala em texto.',
              wraplength=340, style='Muted.TLabel').pack(anchor='w', pady=8)
    ttk.Label(panel, text='Ativo:').pack(anchor='w')
    ttk.Label(panel, textvariable=window.model, wraplength=340).pack(anchor='w', pady=(0, 8))
    ttk.Label(panel, text='Filtrar modelos:').pack(anchor='w')
    window.model_filter = tk.StringVar()
    entry = ttk.Entry(panel, textvariable=window.model_filter)
    entry.pack(fill='x', pady=4)
    window.model_catalog = []
    window.model_filter.trace_add('write', lambda *_args: window._filter_models())
    window.models = ttk.Combobox(panel, textvariable=window.model_choice, width=30)
    window.models.pack(fill='x', pady=4)
    ttk.Label(panel, textvariable=window.model_choice, wraplength=340, style='Muted.TLabel').pack(anchor='w')
    controls = ttk.Frame(panel)
    controls.pack(fill='x', pady=8)
    ttk.Button(controls, text='Atualizar catálogo', command=lambda: window.backend.submit('models')).pack(side='left')
    ttk.Button(controls, text='Usar modelo', style='Accent.TButton',
               command=lambda: window.backend.submit('select_model', window.model_choice.get())).pack(side='left', padx=4)
    ttk.Label(panel, text='O perfil só muda após inicialização bem-sucedida. Ambiente explícito prevalece. '
              'Se um modelo falhar, confira o erro antes de repetir uma ação.',
              wraplength=340, style='Muted.TLabel').pack(anchor='w', pady=8)
    ttk.Label(panel, text='Detalhes do último erro:').pack(anchor='w')
    window.error_details = scrolledtext.ScrolledText(panel, width=30, height=6, wrap='word', state='disabled')
    window.error_details.pack(fill='both', expand=True, pady=4)
