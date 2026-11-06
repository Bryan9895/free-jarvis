"""Explicit Local comparison and human review through the existing GUI worker."""
import math
from time import monotonic
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

from .cancellation import CancellationToken, CancelledError

COMMANDS = frozenset({'comparison_run', 'comparison_load', 'comparison_responses', 'comparison_review', 'comparison_pick'})


def _summary(directory, report):
    models = []
    for name, data in report['models'].items():
        warm = [entry for entry in data['runs'] if entry['phase'] == 'warm']
        p95 = [entry['scenarios'][entry['scenario']]['first_visual_s']['p95'] for entry in warm]
        pss = [entry['memory'].get('peak_tree_pss_kib') for entry in warm if entry['memory'].get('pss_complete')]
        models.append({'name': name, 'turns': sum(len(entry['turns']) for entry in data['runs']),
            'completed': data['completed'],
            'p95': max(p95) if p95 and all(type(v) in (int, float) and math.isfinite(v) for v in p95) else None,
            'pss_kib': max(pss) if len(pss) == len(warm) and pss and all(type(v) in (int, float) for v in pss) else None})
    return {'directory': str(directory), 'state': report['state'], 'models': models}


def dispatch(backend, command, value):
    from . import model_evaluation as evaluation
    from .gui_setup import current_config
    token = CancellationToken(event=backend._capture_cancel, deadline=monotonic() + 14400)
    status = lambda message: backend.events.put(('comparison_status', message))
    try:
        token.check()
        if command == 'comparison_run':
            config = current_config(backend)
            pid = int(value['pid']) if value.get('pid', '').strip() else backend._ollama_session.monitor_pid(config.ollama_host)
            if pid is None:
                status('Inicie o servidor Local ou informe o PID do Ollama externo antes de comparar. Nenhum modelo foi aplicado.')
                return
            def progress(event):
                if 'directory' in event:
                    backend.events.put(('comparison_directory', event['directory']))
                else:
                    status(f"{event['model']} · {event['scenario']} · {event['phase']} · "
                           f"{event['completed']}/{event['expected']}")
            directory, report = evaluation.evaluate(config, value['models'], directory=value['directory'],
                monitor_pid=pid, cancel_token=token, progress=progress)
            backend.events.put(('comparison_report', _summary(directory, report)))
            status({'completed': 'Medições concluídas. Revise as respostas antes de indicar um modelo.',
                    'cancelled': 'Comparação cancelada. Resultados parciais preservados; nenhum modelo indicado.',
                    'failed': 'Comparação falhou. Resultados parciais preservados; confira os componentes.'}[report['state']])
        elif command == 'comparison_load':
            directory, report = evaluation.load(value['directory'])
            backend.events.put(('comparison_report', _summary(directory, report)))
            status('Relatório aberto. A revisão de qualidade exige ação explícita; nenhuma inferência foi repetida.')
        elif command == 'comparison_responses':
            backend.events.put(('comparison_responses', evaluation.responses_for_review(value['directory'])))
        elif command == 'comparison_review':
            result = evaluation.review(value['directory'], value['assessments'])
            status(result['selection'] + '. Preferências preservadas.')
        elif command == 'comparison_pick':
            from .local_provider import OpenJarvisProvider
            model, expected = evaluation.approved_model(value['directory'])
            config = current_config(backend, model)
            provider = OpenJarvisProvider(model=model, host=config.ollama_host, python=config.openjarvis_python)
            try:
                actual = provider._exchange({'operation': 'identity', 'model': model}, cancel_token=token)
                token.check()
                if actual != expected:
                    raise ValueError('Pesos mudaram após o ensaio')
            finally:
                provider.close()
            backend.events.put(('comparison_pick', model))
            status('Modelo elegível copiado para Configuração inicial. Aplique o perfil explicitamente para usá-lo.')
    except CancelledError:
        status('Operação cancelada. Nenhum modelo foi aplicado.')
    except Exception as exc:
        status(f'Operação não concluída ({type(exc).__name__}). Confira servidor/PID, dois modelos instalados, '
               'pasta fora de Git e revisão completa dos arquivos exatos. Nenhum modelo foi aplicado.')


def show_responses(window, rows):
    dialog = tk.Toplevel(window.root)
    dialog.title('Respostas dirigidas para revisão · arquivos privados')
    dialog.geometry('950x650')
    ttk.Label(dialog, text='Revisão humana: confira conteúdo, números e negações. Este ensaio não contém áudio ambiental.',
              wraplength=850).pack(anchor='w', padx=8, pady=8)
    listing = tk.Listbox(dialog, height=7)
    listing.pack(fill='x', padx=8)
    body = scrolledtext.ScrolledText(dialog, wrap='word', state='disabled')
    body.pack(fill='both', expand=True, padx=8, pady=8)
    for index, row in enumerate(rows):
        listing.insert('end', f"{index + 1} · {row['model']} · {row['phase']} · {row['scenario']} · {row['state']}")
    def select(_event=None):
        selected = listing.curselection()
        if selected:
            row = rows[selected[0]]
            body.configure(state='normal')
            body.delete('1.0', 'end')
            body.insert('end', 'Pedido dirigido:\n' + row['request'] + '\n\nResposta:\n' + row['answer'])
            body.configure(state='disabled')
    listing.bind('<<ListboxSelect>>', select)
    if rows:
        listing.selection_set(0)
        select()
    ttk.Button(dialog, text='Fechar revisão', command=dialog.destroy).pack(pady=5)


def handle(window, kind, payload):
    if kind == 'comparison_status':
        window.comparison_status.set(payload)
    elif kind == 'comparison_directory':
        window.comparison_directory.set(payload)
    elif kind == 'comparison_report':
        window.comparison_directory.set(payload['directory'])
        window.comparison_summary.set('Ensaio: ' + payload['state'] + '\n' + '\n'.join(
            f"{row['name']}: {row['turns']} turnos · pior p95 aquecido {row['p95']} s · PSS {row['pss_kib']} KiB"
            for row in payload['models']))
        for widget in window.comparison_review_form.winfo_children(): widget.destroy()
        window.comparison_assessments = {}
        for row in payload['models']:
            ttk.Label(window.comparison_review_form, text=f"{row['name']} · {row['turns']} respostas arquivadas",
                      wraplength=300).pack(anchor='w', pady=(8, 2))
            fields = window.comparison_assessments[row['name']] = {}
            for key, label in (('reviewed', 'Respostas revisadas'), ('adequate', 'Respostas adequadas'),
                               ('critical_errors', 'Erros críticos'), ('oom', 'Ocorrências de falta de memória')):
                line = ttk.Frame(window.comparison_review_form)
                line.pack(fill='x')
                ttk.Label(line, text=label, wraplength=210).pack(side='left')
                fields[key] = tk.StringVar()
                ttk.Entry(line, textvariable=fields[key], width=6).pack(side='right')
    elif kind == 'comparison_responses':
        show_responses(window, payload)
    elif kind == 'comparison_pick':
        window.setup_model.set(payload)
        window.workspace_panels.select(window.setup_panel_index)
        window.setup_status.set('Modelo elegível: ' + payload + '. Aplique o perfil para usar esta seleção.')


def build_comparison_panel(window, tabs):
    from .gui_shell import ScrollPanel
    panel = ScrollPanel(tabs)
    window.comparison_panel_index = len(tabs.panels)
    window.comparison_panel = panel
    tabs.add(panel, text='Comparar modelos')
    content = panel.content
    window.comparison_models = [tk.StringVar(value=window.preferences.local_model), tk.StringVar()]
    window.comparison_pid = tk.StringVar()
    window.comparison_directory = tk.StringVar()
    window.comparison_status = tk.StringVar(value='Prepare e instale os dois modelos antes de iniciar. Não há downloads neste ensaio.')
    window.comparison_summary = tk.StringVar(value='Nenhuma medição carregada.')
    window.comparison_buttons = []
    window.comparison_assessments = {}
    ttk.Label(content, text='Comparar dois modelos Local', font=('DejaVu Sans', 12, 'bold')).pack(anchor='w')
    ttk.Label(content, text='Ensaio longo: 396 turnos ao todo, com 3 frios e 30 aquecidos por cenário/modelo. '
              'Executa arquivos e tarefas somente em pasta temporária. Descarrega pesos entre candidatos. '
              'Parar interrompe o ensaio. Não mede voz nem comprova isolamento de rede.', wraplength=300).pack(anchor='w', pady=8)
    for index, variable in enumerate(window.comparison_models):
        ttk.Label(content, text=f'Modelo {index + 1} já instalado').pack(anchor='w')
        ttk.Entry(content, textvariable=variable).pack(fill='x')
    ttk.Label(content, text='PID Ollama externo (vazio: servidor desta janela)', wraplength=300).pack(anchor='w', pady=(8, 0))
    ttk.Entry(content, textvariable=window.comparison_pid).pack(fill='x')
    def submit(command, value):
        if window.backend.submit(command, value): window.comparison_status.set('Operação solicitada…')
    def button(text, callback):
        control = ttk.Button(content, text=text, command=callback)
        control.pack(fill='x', pady=3)
        window.comparison_buttons.append(control)
        return control
    def start():
        directory = filedialog.askdirectory(parent=window.root, title='Escolha pasta privada fora de Git para o novo ensaio')
        if directory:
            if window.backend.submit('comparison_run', {'directory': directory,
                    'models': [value.get().strip() for value in window.comparison_models], 'pid': window.comparison_pid.get().strip()}):
                window.comparison_directory.set('')
                window.comparison_status.set('Comparação solicitada; aguardando preflight…')
    button('Executar comparação e arquivar respostas', start)
    def open_existing():
        directory = filedialog.askdirectory(parent=window.root, title='Abra pasta de um ensaio existente')
        if directory: submit('comparison_load', {'directory': directory})
    button('Abrir ensaio existente sem inferir', open_existing)
    ttk.Entry(content, textvariable=window.comparison_directory, state='readonly').pack(fill='x', pady=5)
    ttk.Label(content, textvariable=window.comparison_status, wraplength=300).pack(anchor='w', pady=5)
    ttk.Label(content, textvariable=window.comparison_summary, wraplength=300).pack(anchor='w', pady=5)
    window.comparison_cancel = ttk.Button(content, text='Parar comparação', command=window.backend.cancel)
    window.comparison_cancel.pack(fill='x', pady=5)
    button('Ver respostas privadas para revisão', lambda: submit('comparison_responses', {'directory': window.comparison_directory.get()}))
    ttk.Label(content, text='Após revisar todas as respostas, declare as contagens de cada modelo. '
              'Qualidade ≥95%, zero erros críticos/OOM/efeitos indevidos e RAM completa são necessários. '
              'Contagens são declarações humanas, sem avaliação automática do significado.', wraplength=300).pack(anchor='w', pady=8)
    window.comparison_review_form = ttk.Frame(content)
    window.comparison_review_form.pack(fill='x')
    def review():
        try:
            entries = {model: {key: int(value.get()) for key, value in fields.items()}
                       for model, fields in window.comparison_assessments.items()}
        except ValueError:
            window.comparison_status.set('Preencha todas as contagens com números inteiros após revisar as respostas.')
            return
        submit('comparison_review', {'directory': window.comparison_directory.get(), 'assessments': entries})
    button('Registrar revisão e indicar elegível', review)
    button('Copiar elegível para configuração', lambda: submit('comparison_pick', {'directory': window.comparison_directory.get()}))
