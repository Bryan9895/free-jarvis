"""Painel de voz: conversa, seleção de entrada e diagnóstico separados."""
import os
import tkinter as tk
from tkinter import ttk, scrolledtext
from .voice_diagnostics import TEST_PHRASE


def build_voice_panel(window, tabs):
    voice = ttk.Frame(tabs, padding=8)
    tabs.add(voice, text='Voz')
    ttk.Label(voice, text='Voz', font=('DejaVu Sans', 14, 'bold')).pack(anchor='w')
    window.voice_status = tk.StringVar(value='Escuta desativada. Escolha como conversar abaixo.')
    ttk.Label(voice, textvariable=window.voice_status, wraplength=340).pack(fill='x', pady=(4, 10))
    pages = ttk.Notebook(voice)
    pages.pack(fill='both', expand=True)
    window.voice_pages = pages
    talk, microphone, test = (ttk.Frame(pages, padding=8) for _ in range(3))
    for panel, title in ((talk, 'Conversar'), (microphone, 'Microfone'), (test, 'Testar áudio')):
        pages.add(panel, text=title)

    configured = os.getenv('JARVIS_WAKE_MODEL', 'small')
    window.voice_test_model = tk.StringVar(value=configured)
    ttk.Label(talk, text='1. Reconhecimento da sua fala', font=('DejaVu Sans', 11, 'bold')).pack(anchor='w')
    row = ttk.Frame(talk)
    row.pack(fill='x', pady=6)
    ttk.Label(row, text='Whisper:').pack(side='left')
    ttk.Combobox(row, textvariable=window.voice_test_model, values=('tiny', 'base', 'small'),
                 width=9, state='readonly').pack(side='left', padx=6)
    ttk.Label(talk, text='Use o modelo que foi melhor em Testar áudio. Small exige mais memória e tempo na CPU.',
              wraplength=320, style='Muted.TLabel').pack(anchor='w')
    ttk.Button(talk, text='Aplicar modelo e microfone', command=window._apply_voice_settings).pack(fill='x', pady=8)
    ttk.Label(talk, text='2. Escolha como falar', font=('DejaVu Sans', 11, 'bold')).pack(anchor='w', pady=(8, 4))
    window.voice_toggle_button = ttk.Button(talk, text='Ativar escuta contínua', command=window._toggle_voice)
    window.voice_toggle_button.pack(fill='x')
    ttk.Label(talk, text='Contínua: diga “Jarvis” seguido do pedido. Ao terminar de falar, aguarde o reconhecimento.',
              wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=(4, 12))
    window.push_to_talk_button = ttk.Button(talk, text='Apertar para falar · 6 s', style='Accent.TButton',
                                           command=window._push_to_talk)
    window.push_to_talk_button.pack(fill='x')
    ttk.Label(talk, text='Clique uma vez e fale por até 6 segundos. Grava e envia automaticamente; não precisa dizer Jarvis.',
              wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=4)
    window.voice_capture_level = ttk.Progressbar(talk, maximum=100)
    window.voice_capture_level.pack(fill='x', pady=6)
    output = ('Resposta falada: Piper configurado.' if os.getenv('JARVIS_PIPER_MODEL') else
              'Resposta em texto. Para ouvir a resposta, configure a voz Piper.')
    ttk.Label(talk, text=output, wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=6)

    ttk.Label(microphone, text='Entrada de áudio', font=('DejaVu Sans', 11, 'bold')).pack(anchor='w')
    ttk.Label(microphone, text='Conecte o Bluetooth e selecione seu microfone no Ubuntu. Evite entradas .monitor.',
              wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=6)
    window.devices = ttk.Combobox(microphone, textvariable=window.voice_device, width=30)
    window.devices.pack(fill='x', pady=4)
    controls = ttk.Frame(microphone)
    controls.pack(fill='x', pady=4)
    ttk.Button(controls, text='Listar entradas', command=lambda: window.backend.submit('voice_devices')).pack(side='left')
    ttk.Button(controls, text='Verificar', command=lambda: window._voice_test_action('probe')).pack(side='left', padx=4)
    ttk.Label(microphone, text='Se aparecer apenas pulse/default, use a entrada escolhida no Ubuntu. '
              'O campo vazio usa a entrada padrão/configurada.', wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=8)
    ttk.Button(microphone, text='Usar esta entrada na escuta', command=window._apply_voice_settings).pack(fill='x')
    window.voice_device_result = scrolledtext.ScrolledText(microphone, height=6, width=30, wrap='word', state='disabled')
    window.voice_device_result.pack(fill='both', expand=True, pady=8)

    ttk.Label(test, text='Diagnóstico local · não envia pedidos', font=('DejaVu Sans', 10, 'bold')).pack(anchor='w')
    ttk.Label(test, text='Leia a frase durante a gravação:', style='Muted.TLabel').pack(anchor='w', pady=(6, 2))
    window.voice_reference = ttk.Entry(test)
    window.voice_reference.insert(0, TEST_PHRASE)
    window.voice_reference.pack(fill='x')
    row = ttk.Frame(test)
    row.pack(fill='x', pady=6)
    ttk.Label(row, text='Whisper do teste:').pack(side='left')
    ttk.Combobox(row, textvariable=window.voice_test_model, values=('tiny', 'base', 'small'),
                 width=8, state='readonly').pack(side='left', padx=4)
    controls = ttk.Frame(test)
    controls.pack(fill='x')
    for action, label in (('capture', 'Gravar 6 s'), ('replay', 'Ouvir'), ('transcribe', 'Transcrever')):
        ttk.Button(controls, text=label, command=lambda action=action: window._voice_test_action(action)).pack(side='left')
    window.voice_level = ttk.Progressbar(test, maximum=100)
    window.voice_level.pack(fill='x', pady=6)
    window.voice_test_status = tk.StringVar(value='Grave, ouça e compare a mesma amostra.')
    ttk.Label(test, textvariable=window.voice_test_status, wraplength=320).pack(anchor='w')
    window.voice_test_result = scrolledtext.ScrolledText(test, height=6, width=30, wrap='word', state='disabled')
    window.voice_test_result.pack(fill='both', expand=True, pady=6)
    ttk.Button(test, text='Apagar amostra', command=lambda: window._voice_test_action('clear')).pack(anchor='w')
    ttk.Label(test, text='Similaridade vale só para esta frase. Áudio temporário apagado ao substituir ou fechar.',
              wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=4)
