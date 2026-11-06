"""Explicit preparation commands and their Tk presentation; no startup download."""
from dataclasses import replace
import os
from time import monotonic
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog

from .cancellation import CancellationToken, CancelledError

OPERATIONS = {
    'engine': 'Preparar motor Local', 'ollama': 'Instalar Ollama',
    'server': 'Iniciar servidor Local', 'stop_server': 'Parar servidor desta janela',
    'model': 'Baixar modelo de conversa', 'stt': 'Preparar reconhecimento de fala',
    'check': 'Testar inferência Local',
}


def current_config(backend, model=None):
    from .config import Config
    from .local_setup import managed_python
    config = backend.config or Config.from_env()
    return replace(config, local_model=model if model is not None else config.local_model,
        openjarvis_python=os.getenv('JARVIS_OPENJARVIS_PYTHON') or managed_python() or config.openjarvis_python)


def refresh(backend):
    from .doctor import collect, human
    backend.events.put(('setup_report', human(collect(current_config(backend)))))


def run_setup(backend, value):
    from . import local_setup
    if (not isinstance(value, dict) or value.keys() - {'operation', 'model', 'python', 'offline', 'stt_model'}
            or value.get('operation') not in OPERATIONS
            or not isinstance(value.get('model', ''), str)
            or not isinstance(value.get('python', ''), str)
            or type(value.get('offline', False)) is not bool):
        raise ValueError('Configuração inicial inválida')
    operation = value['operation']
    token = CancellationToken(event=backend._capture_cancel, deadline=monotonic() + 3600)
    progress = lambda text: backend.events.put(('setup_status', text))
    try:
        token.check()
        progress(OPERATIONS[operation] + '…')
        model = value.get('model', '').strip()
        if operation in ('model', 'check'):
            from .local_provider import local_model
            local_model(model)
        config = current_config(backend, model or None)
        if operation == 'engine':
            result = local_setup.install_engine(python=value.get('python', ''), offline=value.get('offline', False),
                                                cancel_token=token, progress=progress)
            message = 'Motor Local verificado. O perfil atual foi preservado.'
        elif operation == 'ollama':
            from .ollama_setup import install
            result = install(token=token, progress=progress)
            message = 'Ollama instalado e verificado. Inicie o servidor Local.'
        elif operation == 'server':
            result = backend._ollama_session.start(config.ollama_host, token=token)
            message = ('Servidor desta janela pronto; será encerrado ao fechar Jarvis.' if result['managed']
                       else 'Servidor existente disponível. Seu ciclo de vida e configuração continuam externos.')
        elif operation == 'stop_server':
            closed = backend._ollama_session.close()
            result = {'state': 'OK'}
            message = ('Servidor desta janela encerrado. A conversa Local fica indisponível até iniciar novamente.' if closed
                       else 'Nenhum servidor desta janela para encerrar. Servidores externos foram preservados.')
        elif operation == 'model':
            result = local_setup.pull_model(config, config.local_model, token=token, progress=progress)
            message = 'Pesos baixados e identidade registrada. Teste o modelo antes de aplicar o perfil.'
        elif operation == 'stt':
            result = local_setup.install_stt(value.get('stt_model', 'small'), token=token, progress=progress)
            message = 'Pesos Whisper preparados. Microfone e acurácia ainda precisam de teste.'
        else:
            result = local_setup.check(config, token=token)
            message = 'Inferência textual Local respondeu. Ferramentas, isolamento de rede e áudio físico não testados.'
        token.check()
        backend.events.put(('setup_result', {'operation': operation, 'state': 'OK', 'message': message,
            'model': result.get('model', ''), 'python': result.get('python', '')}))
    except (CancelledError, TimeoutError) as exc:
        backend.events.put(('setup_result', {'operation': operation, 'state': 'Cancelado' if isinstance(exc, CancelledError) else 'Prazo excedido',
            'message': 'Operação interrompida. Componentes já instalados permanecem; nenhuma troca de perfil foi aplicada.'}))
    except Exception as exc:
        # Never forward installer/provider output, credential URLs or tokens to Tk.
        guidance = {
            'engine': 'Confira uv e Python 3.10–3.13 instalado; escolha o interpretador e tente novamente.',
            'ollama': 'Confira acesso à rede, espaço em disco e Python 3.14+ para o instalador Linux.',
            'server': 'Confira instalação Ollama e disponibilidade da porta de loopback.',
            'model': 'Prepare o motor, inicie o servidor e confira nome do modelo, rede e espaço em disco.',
            'stt': 'Confira faster-whisper instalado, rede e espaço para os pesos.',
            'check': 'Prepare o motor, inicie o servidor e baixe o modelo informado.',
            'stop_server': 'Não foi possível concluir a limpeza do servidor desta janela.',
        }
        backend.events.put(('setup_result', {'operation': operation, 'state': 'Falhou',
            'message': f'{OPERATIONS[operation]} falhou ({type(exc).__name__}). {guidance[operation]} '
                       'O perfil anterior foi preservado.'}))
    finally:
        refresh(backend)


def build_setup_panel(window, tabs):
    from .gui_shell import ScrollPanel
    panel = ScrollPanel(tabs)
    window.setup_panel = panel
    window.setup_panel_index = len(tabs.panels)
    tabs.add(panel, text='Configuração inicial')
    content = panel.content
    window.setup_model = tk.StringVar(value=window.preferences.local_model)
    window.setup_python = tk.StringVar()
    window.setup_offline = tk.BooleanVar(value=False)
    window.setup_stt = tk.StringVar(value=window.preferences.stt_model)
    window.setup_status = tk.StringVar(value='Escolha uma etapa. Abrir este painel não baixa arquivos nem testa áudio.')
    window.setup_buttons = []

    def section(title, text):
        ttk.Label(content, text=title, font=('DejaVu Sans', 11, 'bold')).pack(anchor='w', pady=(10, 3))
        ttk.Label(content, text=text, wraplength=300, style='Muted.TLabel').pack(anchor='w')

    def run(operation):
        accepted = window.backend.submit('setup_run', {'operation': operation, 'model': window.setup_model.get().strip(),
            'python': window.setup_python.get().strip(), 'offline': window.setup_offline.get(), 'stt_model': window.setup_stt.get()})
        if accepted:
            window.setup_status.set(OPERATIONS[operation] + ' solicitada…')

    def button(label, command):
        control = ttk.Button(content, text=label, command=command)
        control.pack(fill='x', pady=3)
        window.setup_buttons.append(control)
        return control

    section('1. Preparar o motor Local',
            'Os downloads são explícitos e podem ser grandes. Cada etapa pode ser repetida após falha. '
            'Requer uv e Python compatível já instalados. Seu perfil atual só muda ao aplicar a seleção na etapa 3.')
    ttk.Label(content, text='Python compatível já instalado (opcional)').pack(anchor='w', pady=(5, 0))
    ttk.Entry(content, textvariable=window.setup_python).pack(fill='x')
    def choose_python():
        selected = filedialog.askopenfilename(parent=window.root, title='Escolha Python 3.10–3.13 instalado')
        if selected: window.setup_python.set(selected)
    button('Escolher Python…', choose_python)
    ttk.Checkbutton(content, text='Motor: usar somente cache local', variable=window.setup_offline).pack(anchor='w')
    button('Preparar motor Local', lambda: run('engine'))
    button('Instalar Ollama', lambda: run('ollama'))
    section('2. Preparar o modelo de conversa',
            'Inicie o servidor antes do download. O servidor criado aqui usa CPU e um modelo por vez; '
            'servidores existentes mantêm sua própria configuração.')
    button('Iniciar servidor Local', lambda: run('server'))
    button('Parar servidor desta janela', lambda: run('stop_server'))
    ttk.Label(content, text='Modelo Local a baixar e testar').pack(anchor='w', pady=(5, 0))
    ttk.Entry(content, textvariable=window.setup_model).pack(fill='x')
    button('Baixar modelo informado', lambda: run('model'))
    button('Testar inferência textual Local', lambda: run('check'))
    button('Comparar modelos preparados', lambda: tabs.select(window.comparison_panel_index))
    section('3. Usar o perfil Local',
            'Aplicar prepara uma nova sessão antes de substituir a atual. '
            'Variáveis de ambiente explícitas prevalecem. O teste textual não comprova operação offline.')
    button('Aplicar perfil Local e modelo informado', lambda: window.backend.submit(
        'select_profile', {'profile': 'local', 'model': window.setup_model.get().strip()}))
    section('4. Configurar escuta e voz',
            'Prepare os pesos de reconhecimento e abra Voz para escolher entrada, saída e Piper ou Kokoro. '
            'Gravação e reprodução só começam pelos botões de teste correspondentes.')
    ttk.Combobox(content, textvariable=window.setup_stt, values=('tiny', 'base', 'small'), state='readonly').pack(fill='x')
    button('Preparar pesos Whisper', lambda: run('stt'))
    def open_voice():
        tabs.select(window.voice_panel_index)
    button('Configurar e testar microfone e voz', open_voice)
    ttk.Label(content, textvariable=window.setup_status, wraplength=300).pack(anchor='w', pady=8)
    window.setup_cancel_button = ttk.Button(content, text='Parar operação', command=window.backend.cancel)
    window.setup_cancel_button.pack(fill='x', pady=3)
    button('Atualizar componentes sem teste ativo', lambda: window.backend.submit('setup_refresh'))
    window.setup_report = scrolledtext.ScrolledText(content, width=30, height=12, wrap='word', state='disabled')
    window.setup_report.pack(fill='x', pady=8)
