"""Painel de voz: conversa, seleção de entrada e diagnóstico separados."""
import os
import tkinter as tk
from tkinter import ttk, scrolledtext
from .voice_diagnostics import TEST_PHRASE
from .gui_shell import ScrollPanel


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
    output_scroll = ScrollPanel(pages)
    output_panel = output_scroll.content
    window.voice_output_scroll = output_scroll
    for panel, title in ((talk, 'Conversar'), (microphone, 'Microfone'), (test, 'Diagnóstico'), (output_scroll, 'Saída')):
        pages.add(panel, text=title)

    configured = os.getenv('JARVIS_WAKE_MODEL', window.preferences.stt_model)
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
    window.push_to_talk_button = ttk.Button(talk, text='Falar / terminar pedido', style='Accent.TButton',
                                           command=window._push_to_talk)
    window.push_to_talk_button.pack(fill='x')
    pending = ttk.Frame(talk)
    pending.pack(fill='x', pady=3)
    ttk.Button(pending, text='Continuar pendente', command=lambda: window._push_to_talk(continue_pending=True)).pack(side='left')
    ttk.Button(pending, text='Descartar pendente', command=lambda: window.backend.submit('voice_discard_pending')).pack(side='right')
    ttk.Label(talk, text='Clique e fale. Um segundo de silêncio termina o pedido; outro clique envia. Parar descarta a captura. Não precisa dizer Jarvis.',
              wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=4)
    window.voice_capture_level = ttk.Progressbar(talk, maximum=100)
    window.voice_capture_level.pack(fill='x', pady=6)
    output = ('Voz selecionada; confirme áudio na aba Saída.' if window.preferences.piper_model else
              'Resposta em texto. Selecione e teste uma voz local na aba Saída.')
    window.voice_output_status = tk.StringVar(value=output)
    ttk.Label(talk, textvariable=window.voice_output_status, wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=6)

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

    window.voice_piper_model = tk.StringVar(value=window.preferences.piper_model)
    window.voice_output = tk.StringVar(value=window.preferences.output_device)
    window.voice_silence = tk.StringVar(value=str(window.preferences.silence_ms))
    window.voice_vad_threshold = tk.StringVar(value=str(window.preferences.vad_threshold))
    window.voice_mode = tk.StringVar(value=window.preferences.voice_mode)
    window.voice_followup = tk.StringVar(value=str(window.preferences.followup_seconds))
    window.voice_start_timeout = tk.StringVar(value=str(window.preferences.start_timeout_seconds))
    window.voice_retries = tk.StringVar(value=str(window.preferences.reconnect_attempts))
    window.voice_wake = tk.StringVar(value=window.preferences.wake_manifest)
    ttk.Label(output_panel, text='Voz Piper local · pt-BR', font=('DejaVu Sans', 11, 'bold')).pack(anchor='w')
    ttk.Label(output_panel, text='Selecione .onnx com .onnx.json ou instale Faber: fonte Piper, SHA256 verificado, dataset CC0.',
              wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=4)
    row = ttk.Frame(output_panel)
    row.pack(fill='x', pady=4)
    ttk.Entry(row, textvariable=window.voice_piper_model, width=12).pack(side='left', fill='x', expand=True)
    window.voice_select_button = ttk.Button(row, text='Escolher…', command=window._choose_piper_voice)
    window.voice_select_button.pack(side='left')
    window.voice_install_button = ttk.Button(output_panel, text='Instalar Faber pt-BR (~63 MB)', command=window._install_voice)
    window.voice_install_button.pack(fill='x', pady=2)
    ttk.Label(output_panel, text='Saída Pulse/PipeWire (vazia = padrão)').pack(anchor='w')
    window.voice_output_choice = ttk.Combobox(output_panel, textvariable=window.voice_output, width=22)
    window.voice_output_choice.pack(fill='x', pady=4)
    ttk.Button(output_panel, text='Listar saídas', command=lambda: window.backend.submit('voice_outputs')).pack(anchor='w')
    row = ttk.Frame(output_panel)
    row.pack(fill='x', pady=6)
    ttk.Label(row, text='Silêncio (ms):').pack(side='left')
    ttk.Spinbox(row, from_=600, to=1800, increment=100, textvariable=window.voice_silence, width=5).pack(side='left', padx=4)
    ttk.Combobox(row, textvariable=window.voice_mode, values=('continuous', 'manual', 'muted'),
                 width=11, state='readonly').pack(side='left')
    row = ttk.Frame(output_panel)
    row.pack(fill='x', pady=4)
    ttk.Label(row, text='Limiar VAD (0.1–0.9):').pack(side='left')
    ttk.Spinbox(row, from_=0.1, to=0.9, increment=0.05, textvariable=window.voice_vad_threshold, width=5).pack(side='left', padx=4)
    for label, variable, minimum, maximum in (
            ('Seguimento sem Jarvis (s):', window.voice_followup, 5, 120),
            ('Espera para começar (s):', window.voice_start_timeout, 3, 120),
            ('Tentativas de reconexão:', window.voice_retries, 0, 5)):
        row = ttk.Frame(output_panel)
        row.pack(fill='x', pady=3)
        ttk.Label(row, text=label).pack(side='left')
        ttk.Spinbox(row, from_=minimum, to=maximum, textvariable=variable, width=5).pack(side='right')
    ttk.Label(output_panel, text='Detector acústico Jarvis · manifesto local').pack(anchor='w', pady=(8, 0))
    ttk.Entry(output_panel, textvariable=window.voice_wake).pack(fill='x')
    ttk.Button(output_panel, text='Escolher manifesto do detector…', command=window._choose_wake_manifest).pack(fill='x')
    ttk.Label(output_panel, text='Opcional: exige artefato pt-BR avaliado, licença e hash. Vazio mantém fallback por transcrição identificado.',
              wraplength=300, style='Muted.TLabel').pack(anchor='w')
    window.voice_save_button = ttk.Button(output_panel, text='Salvar voz, entrada e modo', command=window._save_voice_preferences)
    window.voice_save_button.pack(fill='x', pady=4)
    window.voice_test_button = ttk.Button(output_panel, text='Testar voz salva', command=lambda: window.backend.submit(
        'voice_speak', 'A voz local está configurada. Confirme se você ouviu esta frase com clareza.'))
    window.voice_test_button.pack(fill='x', pady=4)
    ttk.Button(output_panel, text='Preparar voz sem reproduzir', command=lambda:
        window.backend.submit('voice_warmup')).pack(fill='x', pady=4)
    ttk.Label(output_panel, text='Ambiente explícito tem precedência. Salvar não comprova saída audível. Piper e player precisam estar instalados.',
              wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=4)
