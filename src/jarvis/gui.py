"""Interface Tkinter leve sobre JarvisService; FCC e SQLite rodam em worker."""
from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from dataclasses import dataclass, field, replace
from tkinter import messagebox, scrolledtext, ttk, filedialog

from .service import JarvisService
from .gui_presenter import status_label, plan_progress, plan_details, action_summary, error_message


@dataclass
class ApprovalRequest:
    action: str
    event: threading.Event = field(default_factory=threading.Event)
    accepted: bool = False


class GuiBackend:
    """Fila de comandos para manter GUI responsiva e conexões SQLite na mesma thread."""

    ACTIONS = frozenset({"ask", "voice_ask", "tool_action", "plan_action", "retry",
                         "voice_record", "voice_speak", "voice_test_probe", "voice_test_capture",
                         "voice_test_replay", "voice_test_transcribe", "voice_test_clear", "voice_push_to_talk", "voice_install"})

    def __init__(self, config, *, auto=True, service_factory=None):
        self.config = config
        self.auto = auto
        self.service_factory = service_factory or JarvisService.from_config
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.service = None
        self._approval = None
        self._voice = None
        self._voice_listener = None
        self._voice_test = None
        self._action_pending = threading.Event()
        self._cancel_queued = threading.Event()
        self._submission_lock = threading.Lock()
        self._closed = threading.Event()
        self._capture_cancel = threading.Event()
        self._capture_finish = threading.Event()
        self._capturing = threading.Event()
        self._conversation = None
        self._speaking_voice = None
        from .preferences import PreferenceStore
        self.preference_store = PreferenceStore()
        self.preferences = self.preference_store.load()
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-gui-worker")

    def start(self):
        self._thread.start()

    def submit(self, command, value=None):
        with self._submission_lock:
            if self._closed.is_set() and command != "shutdown":
                return False
            if command in self.ACTIONS:
                if self._action_pending.is_set():
                    self.events.put(("error", "Aguarde o pedido atual terminar ou cancele-o antes de enviar outro."))
                    return False
                self._action_pending.set()
                self._cancel_queued.clear()
                self._capture_cancel.clear()
            self.commands.put((command, value))
            return True

    def cancel(self):
        self._capture_cancel.set()
        if self._conversation is not None:
            self._conversation.cancel()
        if self._speaking_voice is not None:
            self._speaking_voice.cancel_speech()
        service = self.service
        cancelled = service.cancel_current() if service is not None else False
        if self._action_pending.is_set():
            self._cancel_queued.set()
            cancelled = True
        request = self._approval
        if request is not None:
            request.accepted = False
            request.event.set()
        return cancelled

    def finish_voice_turn(self):
        if not self._capturing.is_set():
            return False
        self._capture_finish.set()
        return True

    def revoke(self):
        service = self.service
        if service is not None:
            service.approval.revoke()
            self.cancel()
            self.events.put(("approval_mode", "revoked"))

    def close(self):
        self._closed.set()
        if self._voice_listener is not None:
            self._voice_listener.stop(timeout=0)
        self.cancel()
        self.submit("shutdown")

    def respond_approval(self, request: ApprovalRequest, accepted: bool):
        request.accepted = accepted
        request.event.set()

    def _approve(self, action):
        request = ApprovalRequest(action)
        self._approval = request
        self.events.put(("approval_request", request))
        while not request.event.wait(0.1):
            if self._closed.is_set():
                break
        self._approval = None
        return request.accepted and not self._closed.is_set()

    def _connect(self):
        self.service = self.service_factory(
            self.config, auto=self.auto, manual_callback=self._approve,
            report=lambda message: self.events.put(("progress", message)))
        self.events.put(("connected", {
            "model": self.service.client.active_model,
            "approval": self.service.approval.mode,
            "capabilities": sorted(self.service.toolkit.capabilities.enabled),
        }))

    def _reconnect(self):
        if self.service is None:
            self._connect()
        else:
            # Mantém navegador/perfis/SQLite e o modelo escolhido; relê o catálogo.
            models = self.service.client.available_models()
            self.events.put(("models", models))
            self.events.put(("reconnected", self.service.client.active_model))

    def _run(self):
        try:
            try:
                self._connect()
            except Exception as exc:
                self.events.put(("connection_error", str(exc)))
            while not self._closed.is_set():
                command, value = self.commands.get()
                if command == "shutdown":
                    break
                action = command in self.ACTIONS
                try:
                    if action and self._cancel_queued.is_set():
                        self.events.put(("progress", "Pedido cancelado antes de iniciar."))
                        continue
                    if action:
                        self.events.put(("busy", True))
                        if self._voice_listener is not None:
                            if command.startswith("voice_test_") or command == "voice_push_to_talk":
                                if not self._voice_listener.pause(timeout=2):
                                    raise RuntimeError("A captura contínua não liberou o microfone. Pare a escuta e tente novamente.")
                            else:
                                self._voice_listener.pause()
                    if command == "retry":
                        self._reconnect()
                    elif self.service is None and command not in {"voice_devices", "voice_listen_start", "voice_listen_stop", "voice_speak", "voice_configure", "voice_outputs", "voice_install"} and not command.startswith("voice_test_"):
                        self.events.put(("error", "Conecte ao FCC antes de executar uma tarefa."))
                    else:
                        self._dispatch(command, value)
                except Exception as exc:
                    if command.startswith("voice_test_"):
                        self.events.put(("voice_test_error", str(exc)))
                    elif command.startswith("voice_"):
                        self.events.put(("voice_status", error_message(exc)[:220]))
                    self.events.put(("connection_error" if command == "retry" else "error", str(exc)))
                finally:
                    if action:
                        self._action_pending.clear()
                        if self._voice_listener is not None:
                            self._voice_listener.resume()
                        self.events.put(("busy", False))
        finally:
            if self._voice_test is not None:
                self._voice_test.close()
            if self.service is not None:
                try:
                    self.service.close()
                except RuntimeError:
                    pass
            self.events.put(("closed", None))

    def _dispatch(self, command, value):
        service = self.service
        if command.startswith("voice_test_"):
            from .voice_diagnostics import VoiceDiagnostics
            if self._voice_test is None:
                self._voice_test = VoiceDiagnostics()
            if command == "voice_test_probe":
                device = value.split(": ", 1)[-1] if value else None
                self.events.put(("voice_test_probe", self._voice_test.probe(device)))
            elif command == "voice_test_capture":
                device = value.split(": ", 1)[-1] if value else None
                self.events.put(("voice_test_status", "Fale agora por 6 segundos. A escuta de comandos está pausada."))
                result = self._voice_test.capture(device, on_level=lambda level: self.events.put(("voice_test_level", level)))
                self.events.put(("voice_test_capture", result))
            elif command == "voice_test_replay":
                self.events.put(("voice_test_status", "Reproduzindo na saída padrão do Ubuntu…"))
                self.events.put(("voice_test_replay", self._voice_test.replay()))
            elif command == "voice_test_transcribe":
                self.events.put(("voice_test_status", "Transcrevendo localmente; o primeiro uso pode baixar/carregar o modelo…"))
                self.events.put(("voice_test_transcript", self._voice_test.transcribe(value["model"], value["expected"])))
            elif command == "voice_test_clear":
                self._voice_test.close()
                self.events.put(("voice_test_status", "Amostra apagada. Grave outra quando quiser."))
            else:
                raise ValueError("Teste de voz desconhecido")
        elif command == "plan_action":
            action, argument = value
            try:
                result = service.plan_action(action, argument)
                self.events.put(("plan", result))
            finally:
                self.events.put(("plan", service.planner.snapshot()))
        elif command == "plan_history":
            self.events.put(("plan_history", service.planner.history(20)))
        elif command == "tool_action":
            name, arguments = value
            allowed = {"task_list", "task_add", "task_update", "browser_tabs",
                       "browser_new_tab", "browser_select_tab", "browser_close_tab",
                       "place_window", "manage_window", "arrange_windows"}
            if name not in allowed:
                raise ValueError("Ação de interface desconhecida")
            outcome = service.toolkit.execute(name, arguments)
            if "error" in outcome:
                raise RuntimeError(outcome["error"])
            detail = outcome.get("result", {})
            self.events.put(("action_result", detail))
            if name.startswith("task_"):
                refreshed = service.toolkit.execute("task_list", {})
                self.events.put(("task_board", refreshed.get("result", {})))
            elif name.startswith("browser_"):
                refreshed = service.toolkit.execute("browser_tabs", {})
                self.events.put(("browser_tabs", refreshed.get("result", {})))
        elif command == "ask":
            if self._voice_listener is not None:
                self._voice_listener.pause()
            self.events.put(("busy", True))
            try:
                self._conversation_turn(value)
                self.events.put(("metrics", service.agent.last_metrics))
                self.events.put(("plan", service.planner.snapshot()))
            finally:
                if self._voice_listener is not None:
                    self._voice_listener.resume()
                self.events.put(("busy", False))
        elif command == "snapshot":
            self.events.put(("plan", service.planner.snapshot()))
        elif command == "models":
            self.events.put(("models", service.client.available_models()))
        elif command == "select_model":
            service.client.select_model(value)
            service.agent.model = value
            self.preferences = replace(self.preferences, conversation_model=value)
            self.preference_store.save(self.preferences)
            self.events.put(("model", value))
        elif command == "approval_mode":
            service.approval.set_mode(value)
            self.events.put(("approval_mode", service.approval.mode))
        elif command == "capabilities":
            service.set_capabilities(set(value))
            self.events.put(("capabilities", sorted(service.toolkit.capabilities.enabled)))
        elif command == "profiles":
            result = service.toolkit.execute("list_desktop_profiles", {})
            detail = result.get("result", {})
            if not isinstance(detail, dict) or detail.get("status") != "listed":
                raise RuntimeError(result.get("error") or "Perfis indisponíveis")
            self.events.put(("profiles", [item["name"] for item in detail["profiles"]]))
        elif command == "history":
            self.events.put(("history", {
                "turns": service.memory.recent(30), "plans": service.planner.history(10)}))
        elif command == "voice_record":
            from .voice import VoiceIO
            device = value.split(": ", 1)[-1] if value else None
            voice = VoiceIO(model=os.getenv("JARVIS_WHISPER_MODEL", "tiny"),
                            language=os.getenv("JARVIS_LANGUAGE", "pt"), device=device)
            recording = voice.record_turn(cancel=self._capture_cancel)
            try:
                transcript = voice.transcribe(recording)
                if not self._capture_cancel.is_set():
                    self.events.put(("transcript", transcript))
            finally:
                recording.unlink(missing_ok=True)
        elif command == "voice_listen_start":
            options = value if isinstance(value, dict) else {"device": value}
            model = os.getenv('JARVIS_WHISPER_MODEL', options.get("model") or os.getenv("JARVIS_WAKE_MODEL", "small"))
            if not isinstance(model, str) or not model.strip():
                raise ValueError("Escolha um modelo Whisper válido para a escuta.")
            if self._voice_listener is not None:
                if self._voice_listener.stop() is False:
                    raise RuntimeError("A escuta anterior ainda está encerrando. Aguarde e tente aplicar novamente.")
            from .voice import VoiceIO, WakeWordConversation
            selected = os.getenv('JARVIS_AUDIO_DEVICE', options.get("device"))
            device = selected.split(": ", 1)[-1] if selected else None
            self._voice = VoiceIO(model=model,
                                  language=os.getenv("JARVIS_LANGUAGE", "pt"),
                                  piper_model=os.getenv("JARVIS_PIPER_MODEL", ""),
                                  device=device)
            self._voice_listener = WakeWordConversation(
                self._voice, on_command=lambda text: self.submit("voice_ask", text),
                on_status=lambda text: self.events.put(("voice_status", f"Whisper {model}: {text}")),
                on_transcript=lambda text: self.events.put(("voice_heard", text)),
                device=device)
            self.events.put(("voice_listening", True))
            self._voice_listener.start()
        elif command == 'voice_install':
            from .voice_setup import install_faber
            model = install_faber(cancel=self._capture_cancel,
                progress=lambda message: self.events.put(('voice_status', message)))
            if not self._capture_cancel.is_set():
                self._dispatch('voice_configure', {'piper_model': str(model)})
                self.events.put(('voice_installed', str(model)))
        elif command == "voice_configure":
            preferences = replace(self.preferences, **value).validate()
            self.preference_store.save(preferences)
            self.preferences = preferences
            if preferences.voice_mode != 'continuous' and self._voice_listener is not None:
                if not self._voice_listener.stop():
                    raise RuntimeError('A escuta ainda está encerrando; aguarde antes de trocar a entrada')
                self._voice_listener = None
                self.events.put(('voice_listening', False))
            if self._voice is not None:
                effective = preferences.effective()
                from pathlib import Path
                self._voice.piper_model = Path(effective.piper_model).expanduser() if effective.piper_model else None
                self._voice.output_device = effective.output_device
                self._voice.silence_seconds = effective.silence_ms / 1000
                self._voice.vad_threshold = effective.vad_threshold
                if self._voice_listener is not None:
                    self._voice_listener.silence_seconds = self._voice.silence_seconds
            self.events.put(("voice_status", "Preferências salvas. Ambiente explícito tem precedência. Teste a voz para confirmar a saída."))
        elif command == "voice_outputs":
            from .voice import VoiceIO
            self.events.put(("voice_outputs", VoiceIO.output_devices()))
        elif command == "voice_listen_stop":
            if self._voice_listener is not None:
                self._voice_listener.stop()
                self._voice_listener = None
            self.events.put(("voice_listening", False))
        elif command == "voice_push_to_talk":
            from .voice import VoiceIO
            device = os.getenv('JARVIS_AUDIO_DEVICE', value.get("device"))
            device = device.split(": ", 1)[-1] if device else None
            model = os.getenv('JARVIS_WHISPER_MODEL', value.get("model") or "small")
            configured_device = device if device is not None else os.getenv("JARVIS_AUDIO_DEVICE")
            voice = self._voice
            if voice is None or voice.model_name != model or voice.device != configured_device:
                voice = VoiceIO(model=model, language=os.getenv("JARVIS_LANGUAGE", "pt"),
                                piper_model=os.getenv("JARVIS_PIPER_MODEL", ""), device=device)
            self._capture_finish.clear()
            self._capturing.set()
            self.events.put(("voice_capturing", True))
            self.events.put(("voice_status", "Ouvindo. Termine com um segundo de silêncio ou clique novamente para enviar."))
            try:
                recording = voice.record_turn(cancel=self._capture_cancel, finish=self._capture_finish,
                    on_level=lambda level: self.events.put(("voice_capture_level", level)))
            finally:
                self._capturing.clear()
                self.events.put(("voice_capturing", False))
            try:
                self.events.put(("voice_status", f"Whisper {model}: transcrevendo seu pedido…"))
                transcript = voice.transcribe(recording)
                if self._capture_cancel.is_set() or self._closed.is_set():
                    return
                self.events.put(("voice_heard", transcript))
            finally:
                recording.unlink(missing_ok=True)
            self._voice = voice
            self._dispatch("voice_ask", transcript)
        elif command == "voice_ask":
            self.events.put(("voice_transcript", value))
            self.events.put(("busy", True))
            try:
                self._conversation_turn(value, voice=self._voice)
                self.events.put(("metrics", service.agent.last_metrics))
                self.events.put(("plan", service.planner.snapshot()))
            finally:
                if self._voice_listener is not None:
                    self._voice_listener.resume()
                self.events.put(("busy", False))
        elif command == "voice_devices":
            from .voice import VoiceIO
            self.events.put(("voice_devices", [f"{index}: {name}"
                                             for index, name in VoiceIO.input_devices()]))
        elif command == "voice_speak":
            from .voice import VoiceIO
            voice = VoiceIO(piper_model=os.getenv("JARVIS_PIPER_MODEL", ""))
            voice.prepare_speech()
            self._speaking_voice = voice
            try:
                self.events.put(("voice_status", voice.speak(value)))
            finally:
                self._speaking_voice = None

    def _conversation_turn(self, message, *, voice=None):
        from .conversation import ConversationController
        if self._conversation is None or self._conversation.service is not self.service:
            self._conversation = ConversationController(self.service,
                emit=lambda event: self.events.put(("conversation_event", event)),
                on_end=lambda: self._dispatch('voice_listen_stop', None))
        return self._conversation.run(message, voice=voice,
            display=lambda answer: self.events.put(("answer", answer)))


class JarvisWindow:
    def __init__(self, root, backend: GuiBackend):
        self.root, self.backend = root, backend
        self.last_answer = ""
        from .gui_theme import apply_theme
        self._style = apply_theme(root)
        root.title("JARVIS | Conversa")
        root.geometry("1240x720")
        root.minsize(1040, 640)
        self.connection = tk.StringVar(value="Conectando ao FCC…")
        self.model = tk.StringVar()
        self.model_choice = tk.StringVar()
        self.model_summary = tk.StringVar(value="Modelo de conversa: conectando…")
        self.approval_mode = tk.StringVar(value="auto")
        self.voice_device = tk.StringVar()
        from .preferences import PreferenceStore
        self.preference_store = PreferenceStore()
        self.preferences = self.preference_store.load().effective()
        self.voice_device.set(self.preferences.audio_device)
        self.voice_heard = tk.StringVar(value="Última fala: aguardando áudio")
        self.voice_listening = False
        self._operation_error = False
        self._turn_state = None
        self.capability_vars = {}
        self._build()
        if self.preference_store.error:
            self.voice_status.set('Preferências inválidas; padrões usados: ' + self.preference_store.error)
        root.protocol("WM_DELETE_WINDOW", self._close)
        self.backend.start()
        self._poll_timer = root.after(100, self._poll)
        root.bind('<Destroy>', self._destroy, add='+')

    def _build(self):
        from .gui_shell import WorkspacePanels, AssistantHud
        from .gui_theme import PANEL, TEXT, ACCENT, BORDER
        header = ttk.Frame(self.root, padding=(18, 10))
        header.pack(fill="x")
        ttk.Label(header, text="J /", style="Brand.TLabel").pack(side="left", padx=(0, 16))
        ttk.Label(header, textvariable=self.connection, style="Muted.TLabel").pack(side="left", padx=4)
        ttk.Button(header, text="Reconectar", command=lambda: self.backend.submit("retry")).pack(side="left")
        ttk.Button(header, text="Configurações", command=self._toggle_settings).pack(side='right')
        ttk.Label(header, textvariable=self.model_summary, style="Muted.TLabel").pack(side="left", padx=12)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        navigation = ttk.Frame(body, width=175, padding=(0, 10, 10, 0))
        self._navigation = navigation
        navigation.pack(side="left", fill="y")
        navigation.pack_propagate(False)
        ttk.Label(navigation, text="CONFIGURAÇÕES / AVANÇADO", style="Muted.TLabel",
                  font=("DejaVu Sans", 8, "bold")).pack(anchor="w", pady=(0, 12))
        split = ttk.PanedWindow(body, orient="horizontal")
        self._split = split
        split.pack(side="left", fill="both", expand=True)
        conversation = ttk.Frame(split, padding=(4, 0, 12, 0))
        tabs = WorkspacePanels(split, navigation)
        self.workspace_panels = tabs
        split.add(conversation, weight=3)
        split.add(tabs, weight=2)

        self.hud = AssistantHud(conversation)
        self.hud.pack(fill="x")
        ttk.Label(conversation, text="CONVERSA", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(conversation, textvariable=self.voice_heard, wraplength=380,
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self.chat = scrolledtext.ScrolledText(conversation, wrap="word", state="disabled",
            width=42, height=8, background=PANEL, foreground=TEXT, insertbackground=ACCENT,
            relief="flat", borderwidth=0, padx=16, pady=14, font=("DejaVu Sans", 10))
        self.chat.tag_configure("speaker", foreground=ACCENT, font=("DejaVu Sans", 10, "bold"))
        self.chat.pack(fill="both", expand=True)
        send = ttk.Frame(conversation)
        send.pack(fill="x", pady=6)
        self.message = ttk.Entry(send)
        self.message.pack(side="left", fill="x", expand=True)
        self.message.bind("<Return>", lambda _event: self._send())
        self.send_button = ttk.Button(send, text="Enviar", style="Accent.TButton", command=self._send)
        self.send_button.pack(side="left", padx=3)
        audio_controls = ttk.Frame(conversation)
        audio_controls.pack(fill="x", pady=(0, 5))
        self.voice_quick = ttk.Button(audio_controls, text="Voz: desligada", command=self._toggle_voice)
        self.voice_quick.pack(side="left")
        self.push_to_talk_quick = ttk.Button(send, text="Falar / terminar", command=self._push_to_talk)
        self.push_to_talk_quick.pack(side="left")
        ttk.Button(audio_controls, text="Ler resposta", command=lambda: self.backend.submit(
            "voice_speak", self.last_answer)).pack(side="left")
        ttk.Button(audio_controls, text="Cancelar pedido", command=self._cancel).pack(side="left")

        tasks = ttk.Frame(tabs, padding=8)
        tabs.add(tasks, text="Plano em execução")
        self.plan_status = tk.StringVar(value="Sem plano")
        ttk.Label(tasks, textvariable=self.plan_status).pack(anchor="w")
        self.steps = ttk.Treeview(tasks, height=5, columns=("id", "status", "description"), show="headings")
        for key, title, width in (("id", "#", 35), ("status", "Estado", 110),
                                  ("description", "Etapa", 260)):
            self.steps.heading(key, text=title)
            self.steps.column(key, width=width)
        self.steps.pack(fill="both", expand=True)
        self.plan_progress = ttk.Progressbar(tasks, mode="determinate", maximum=1)
        self.plan_progress.pack(fill="x", pady=5)
        self.plan_goal = ttk.Entry(tasks)
        self.plan_goal.pack(fill="x", pady=3)
        ttk.Label(tasks, text="Escreva um objetivo e crie um plano antes de executar.",
                  wraplength=320, style="Muted.TLabel").pack(anchor="w")
        controls = ttk.Frame(tasks)
        controls.pack(fill="x")
        for label, action in (("Criar plano", "prepare"), ("Executar", "execute"), ("Retomar", "resume")):
            ttk.Button(controls, text=label, command=lambda action=action: self._plan_action(action)).pack(side="left", padx=2)
        recovery = ttk.Frame(tasks)
        recovery.pack(fill="x", pady=3)
        ttk.Button(recovery, text="Repetir etapa", command=lambda: self._plan_action("resolve", "retry")).pack(side="left")
        ttk.Button(recovery, text="Ignorar etapa", command=lambda: self._plan_action("resolve", "skip")).pack(side="left")
        ttk.Button(recovery, text="Cancelar plano", command=lambda: self._plan_action("cancel")).pack(side="left")
        self.saved_plans = ttk.Combobox(tasks, state="readonly")
        self.saved_plans.pack(fill="x", pady=3)
        history_controls = ttk.Frame(tasks)
        history_controls.pack(fill="x")
        ttk.Button(history_controls, text="Histórico", command=lambda: self.backend.submit("plan_history")).pack(side="left")
        ttk.Button(history_controls, text="Selecionar", command=self._select_plan).pack(side="left")
        ttk.Button(history_controls, text="Atualizar", command=lambda: self.backend.submit("snapshot")).pack(side="left")
        self.plan_detail_text = scrolledtext.ScrolledText(tasks, width=35, height=5, wrap="word", state="disabled")
        self.plan_detail_text.pack(fill="x", pady=5)

        board = ttk.Frame(tabs, padding=8)
        tabs.add(board, text="Minhas tarefas")
        ttk.Label(board, text="Lista pessoal; concluir um item não executa um plano.").pack(anchor="w")
        self.task_title = ttk.Entry(board)
        self.task_title.pack(fill="x")
        self.task_priority = tk.StringVar(value="2")
        ttk.Combobox(board, textvariable=self.task_priority, values=("1", "2", "3"),
                     state="readonly").pack(fill="x")
        ttk.Button(board, text="Adicionar tarefa", command=lambda: self._tool_action(
            "task_add", {"title": self.task_title.get(), "priority": int(self.task_priority.get())})).pack(fill="x")
        self.task_board = ttk.Treeview(board, columns=("id", "title", "state", "priority"), show="headings")
        for key, label in (("id", "#"), ("title", "Tarefa"), ("state", "Estado"), ("priority", "Prioridade")):
            self.task_board.heading(key, text=label)
            self.task_board.column(key, width=120 if key == "title" else 70)
        self.task_board.pack(fill="both", expand=True)
        for state, label in (("pending", "Pendente"), ("in_progress", "Em andamento"), ("done", "Concluída")):
            ttk.Button(board, text=label, command=lambda state=state: self._selected_action(
                self.task_board, "task_update", "task_id", status=state)).pack(side="left")
        ttk.Button(board, text="Atualizar", command=lambda: self._tool_action("task_list", {})).pack()

        browser_panel = ttk.Frame(tabs, padding=8)
        tabs.add(browser_panel, text="Abas gerenciadas")
        ttk.Label(browser_panel, text="Chromium do Jarvis; não controla abas do Firefox pessoal.").pack(anchor="w")
        self.tab_url = ttk.Entry(browser_panel)
        self.tab_url.pack(fill="x")
        ttk.Button(browser_panel, text="Abrir URL em nova aba", command=lambda: self._tool_action(
            "browser_new_tab", {"url": self.tab_url.get()})).pack(fill="x")
        self.browser_tabs = ttk.Treeview(browser_panel, columns=("id", "title", "url"), show="headings")
        for key, label in (("id", "#"), ("title", "Título"), ("url", "URL")):
            self.browser_tabs.heading(key, text=label)
            self.browser_tabs.column(key, width=40 if key == "id" else 160)
        self.browser_tabs.pack(fill="both", expand=True)
        ttk.Button(browser_panel, text="Atualizar abas", command=lambda: self._tool_action("browser_tabs", {})).pack(fill="x")
        for action, label in (("browser_select_tab", "Selecionar aba"), ("browser_close_tab", "Fechar aba")):
            ttk.Button(browser_panel, text=label, command=lambda action=action: self._selected_action(
                self.browser_tabs, action, "tab_id")).pack(fill="x")

        windows = ttk.Frame(tabs, padding=8)
        tabs.add(windows, text="Janelas")
        ttk.Label(windows, text="Aplicativo (use o chat para desambiguar pelo título)").pack(anchor="w")
        self.window_app = ttk.Entry(windows)
        self.window_app.pack(fill="x")
        for position, label in (("left", "Metade esquerda"), ("right", "Metade direita"), ("center", "Centralizar")):
            ttk.Button(windows, text=label, command=lambda position=position: self._tool_action(
                "place_window", {"app": self.window_app.get(), "position": position})).pack(fill="x")
        for action, label in (("minimize", "Minimizar"), ("maximize", "Maximizar"), ("restore", "Restaurar")):
            ttk.Button(windows, text=label, command=lambda action=action: self._tool_action(
                "manage_window", {"app": self.window_app.get(), "action": action})).pack(fill="x")
        ttk.Label(windows, text="Segundo aplicativo para organizar lado a lado").pack(anchor="w")
        self.second_app = ttk.Entry(windows)
        self.second_app.pack(fill="x")
        ttk.Button(windows, text="Organizar lado a lado", command=lambda: self._tool_action(
            "arrange_windows", {"left_app": self.window_app.get(), "right_app": self.second_app.get()})).pack(fill="x")

        permissions = ttk.Frame(tabs, padding=8)
        tabs.add(permissions, text="Permissões")
        ttk.Label(permissions, text="Modo da sessão").pack(anchor="w")
        ttk.Combobox(permissions, textvariable=self.approval_mode,
                     values=("auto", "manual"), state="readonly").pack(fill="x")
        ttk.Button(permissions, text="Aplicar modo", command=lambda: self.backend.submit(
            "approval_mode", self.approval_mode.get())).pack(fill="x")
        ttk.Button(permissions, text="Revogar e cancelar", command=self._revoke).pack(fill="x", pady=5)
        ttk.Label(permissions, text="Capacidades habilitadas").pack(anchor="w", pady=(8, 0))
        self.capabilities_frame = ttk.Frame(permissions)
        self.capabilities_frame.pack(fill="both", expand=True)
        ttk.Button(permissions, text="Aplicar capacidades", command=self._apply_capabilities).pack(fill="x")

        profiles = ttk.Frame(tabs, padding=8)
        tabs.add(profiles, text="Ambientes")
        self.profiles = tk.Listbox(profiles)
        self.profiles.pack(fill="both", expand=True)
        ttk.Button(profiles, text="Atualizar", command=lambda: self.backend.submit("profiles")).pack(fill="x")
        ttk.Button(profiles, text="Restaurar selecionado", command=self._restore_profile).pack(fill="x")

        history = ttk.Frame(tabs, padding=8)
        tabs.add(history, text="Histórico")
        self.history = scrolledtext.ScrolledText(history, width=35, wrap="word", state="disabled")
        self.history.pack(fill="both", expand=True)
        ttk.Button(history, text="Atualizar", command=lambda: self.backend.submit("history")).pack()

        metrics = ttk.Frame(tabs, padding=8)
        tabs.add(metrics, text="Métricas")
        self.metrics = scrolledtext.ScrolledText(metrics, width=35, wrap="word", state="disabled")
        self.metrics.pack(fill="both", expand=True)

        from .gui_models import build_models_panel
        from .gui_voice import build_voice_panel
        self.models_panel_index = len(tabs.panels)
        build_models_panel(self, tabs)
        build_voice_panel(self, tabs)
        self._settings_open = True
        self._toggle_settings()

    def _toggle_settings(self):
        self._settings_open = not getattr(self, '_settings_open', False)
        if self._settings_open:
            self._navigation.pack(side='left', fill='y', before=self._split)
            self._split.add(self.workspace_panels, weight=2)
        else:
            self._navigation.pack_forget()
            self._split.forget(self.workspace_panels)

    def _write(self, widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", value)
        widget.configure(state="disabled")

    def _append_chat(self, label, value):
        self.chat.configure(state="normal")
        self.chat.insert("end", label.upper() + "\n", "speaker")
        self.chat.insert("end", str(value) + "\n\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _send(self):
        message = self.message.get().strip()
        if message and self.backend.submit("ask", message):
            self.message.delete(0, "end")
            self._append_chat("Você", message)

    def _plan_action(self, action, value=None):
        if action == "prepare":
            value = self.plan_goal.get().strip()
            if not value:
                self._append_chat("Sistema", "Informe o objetivo do plano.")
                return
        self.backend.submit("plan_action", (action, value))

    def _select_plan(self):
        selected = self.saved_plans.get()
        if selected:
            plan_id = int(selected.split(" · ", 1)[0].lstrip("#"))
            self._plan_action("select", plan_id)

    def _cancel(self):
        if self.backend.cancel():
            self._append_chat("Sistema", "Cancelamento solicitado; aguardando a chamada atual terminar.")

    def _tool_action(self, name, arguments):
        self.backend.submit("tool_action", (name, arguments))

    def _selected_action(self, widget, name, id_key, **arguments):
        selected = widget.selection()
        if not selected:
            self._append_chat("Sistema", "Selecione um item primeiro.")
            return
        arguments[id_key] = int(widget.item(selected[0], "values")[0])
        self._tool_action(name, arguments)

    def _voice_test_action(self, action):
        value = ({"model": self.voice_test_model.get(), "expected": self.voice_reference.get()}
                 if action == "transcribe" else self.voice_device.get())
        if self.backend.submit("voice_test_" + action, value):
            if action == "capture":
                self.voice_level.configure(value=0)
                self._write(self.voice_test_result, "")
            self.voice_test_status.set("Preparando teste…")

    def _toggle_voice(self):
        if self.voice_listening:
            self.backend.submit("voice_listen_stop")
        else:
            self._apply_voice_settings()

    def _apply_voice_settings(self):
        self.backend.submit("voice_listen_start", {
            "device": self.voice_device.get(), "model": self.voice_test_model.get()})

    def _save_voice_preferences(self):
        try:
            silence_ms = int(self.voice_silence.get())
            vad_threshold = float(self.voice_vad_threshold.get())
        except ValueError:
            self.voice_status.set('Confira silêncio (600–1800 ms) e limiar VAD (0.1–0.9).')
            return
        self.backend.submit('voice_configure', {
            'stt_model': self.voice_test_model.get(), 'audio_device': self.voice_device.get(),
            'piper_model': self.voice_piper_model.get(), 'output_device': self.voice_output.get(),
            'silence_ms': silence_ms, 'vad_threshold': vad_threshold, 'voice_mode': self.voice_mode.get()})

    def _choose_piper_voice(self):
        filename = filedialog.askopenfilename(title='Selecionar voz Piper local (.onnx)',
                                             filetypes=[('Modelo Piper', '*.onnx')])
        if filename:
            self.voice_piper_model.set(filename)

    def _push_to_talk(self):
        if self.backend.finish_voice_turn():
            return
        if self.backend.submit("voice_push_to_talk", {
                "device": self.voice_device.get(), "model": self.voice_test_model.get()}):
            self.voice_capture_level.configure(value=0)
            self.voice_status.set("Preparando gravação. Aguarde Fale agora…")

    def _filter_models(self):
        query = self.model_filter.get().casefold().strip()
        self.models.configure(values=[model for model in self.model_catalog if query in model.casefold()])

    def _show_model(self, model):
        self.model.set(model)
        self.model_choice.set(model)
        short = model if len(model) <= 48 else model[:45] + '…'
        self.model_summary.set('Conversa: ' + short)

    def _revoke(self):
        self.backend.revoke()
        self.approval_mode.set("manual")
        self._append_chat("Sistema", "Sessão revogada; novas ações locais serão recusadas.")

    def _apply_capabilities(self):
        enabled = [name for name, selected in self.capability_vars.items() if selected.get()]
        self.backend.submit("capabilities", enabled)

    def _restore_profile(self):
        selection = self.profiles.curselection()
        if selection:
            name = self.profiles.get(selection[0])
            message = f"Jarvis, restaure meu ambiente {name}"
            self._append_chat("Você", message)
            self.backend.submit("ask", message)

    def _poll(self):
        self._poll_timer = None
        try:
            while True:
                kind, payload = self.backend.events.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self._poll_timer = self.root.after(100, self._poll)

    def _destroy(self, event):
        if event.widget is self.root and self._poll_timer is not None:
            self.root.after_cancel(self._poll_timer)
            self._poll_timer = None

    def _handle(self, kind, payload):
        if kind == "connected":
            self.connection.set("FCC conectado · pronto para conversar")
            self._show_model(payload["model"])
            self.approval_mode.set(payload["approval"])
            self._set_capabilities(payload["capabilities"])
            self.backend.submit("snapshot")
            self.hud.set_state("PRONTO", "Digite ou diga Jarvis seguido do pedido")
            if os.getenv("JARVIS_GUI_VOICE", "1") != "0" and self.preferences.voice_mode == 'continuous':
                self._apply_voice_settings()
        elif kind == "reconnected":
            self.connection.set("Catálogo FCC atualizado · inferência ainda não testada")
            self._show_model(payload)
            self._append_chat("Sistema", "Conexão restabelecida; catálogo atualizado.")
        elif kind == "connection_error":
            self.connection.set("FCC indisponível")
            self.hud.set_state("SEM CONEXÃO", "Confira o servidor FCC e use Reconectar")
            self._append_chat("Sistema", payload)
        elif kind == "answer":
            self.last_answer = payload
            self.hud.set_state("RESPOSTA RECEBIDA", "Conversa e operações no mesmo lugar")
            self._append_chat("JARVIS", payload)
        elif kind == "error":
            self._operation_error = True
            self._append_chat("Erro", error_message(payload))
            self._write(self.error_details, str(payload))
            self.hud.set_state("PEDIDO NÃO CONCLUÍDO", "Confira o erro na conversa")
            if 'http 404' in str(payload).casefold() and '/v1/responses' in str(payload):
                self.voice_status.set("Modelo de conversa indisponível (HTTP 404). Abra Modelos e escolha outro.")
        elif kind == "progress":
            self._append_chat("Etapa", payload)
        elif kind == "busy":
            if payload:
                self._operation_error = False
                self._turn_state = None
            if payload or (not self._operation_error and not self._turn_state):
                self.hud.set_state("PROCESSANDO" if payload else "PRONTO",
                                   "Executando seu pedido" if payload else "Aguardando seu próximo pedido", active=bool(payload))
            self.send_button.configure(state="disabled" if payload else "normal")
            for button in (self.push_to_talk_button, self.push_to_talk_quick):
                button.configure(state="disabled" if payload else "normal")
        elif kind == "metrics":
            self._write(self.metrics, json.dumps(payload, ensure_ascii=False, indent=2))
        elif kind == "plan":
            verified, total = plan_progress(payload)
            self.plan_status.set(f"{status_label(payload.get('status', 'no_plan'))} · {verified}/{total} verificadas")
            self.plan_progress.configure(maximum=max(total, 1), value=verified)
            self._write(self.plan_detail_text, plan_details(payload))
            self.steps.delete(*self.steps.get_children())
            for step in payload.get("steps", []):
                self.steps.insert("", "end", values=(step.get("id"), status_label(step.get("status", "pending")),
                                                     step.get("description")))
        elif kind == "plan_history":
            values = [f"#{plan['id']} · {plan.get('goal', '')[:65]}" for plan in payload if plan.get('id')]
            self.saved_plans.configure(values=values)
            if values:
                self.saved_plans.set(values[0])
        elif kind == "action_result":
            self._append_chat("Ação", action_summary(payload))
        elif kind == "task_board":
            if payload.get("status") == "listed":
                self.task_board.delete(*self.task_board.get_children())
                for task in payload["tasks"]:
                    self.task_board.insert("", "end", values=(task["id"], task["title"], status_label(task["state"]), task["priority"]))
        elif kind == "browser_tabs":
            if payload.get("status") == "listed":
                self.browser_tabs.delete(*self.browser_tabs.get_children())
                for tab in payload["tabs"]:
                    self.browser_tabs.insert("", "end", values=(tab["id"], tab["title"], tab["url"]))
        elif kind == "models":
            self.model_catalog = list(payload)
            self._filter_models()
        elif kind == "model":
            self._show_model(payload)
            self._append_chat("Sistema", "Modelo de conversa selecionado: " + payload + ". Repita o pedido para testar a resposta.")
        elif kind == "approval_mode":
            self.approval_mode.set(payload)
        elif kind == "capabilities":
            self._set_capabilities(payload)
        elif kind == "profiles":
            self.profiles.delete(0, "end")
            for name in payload:
                self.profiles.insert("end", name)
        elif kind == "history":
            self._write(self.history, json.dumps(payload, ensure_ascii=False, indent=2))
        elif kind == "transcript":
            self.message.delete(0, "end")
            self.message.insert(0, payload)
            self._append_chat("Voz", "Transcrição pronta para revisão antes de enviar.")
        elif kind == "voice_transcript":
            self._append_chat("Você (voz)", payload)
        elif kind == "voice_heard":
            self.voice_heard.set("Última fala: " + str(payload)[:140])
        elif kind == "voice_capturing":
            for button in (self.push_to_talk_button, self.push_to_talk_quick):
                button.configure(state='normal' if payload else 'disabled')
        elif kind == "conversation_event":
            self._turn_state = payload.state
            labels = {'executando': 'Executando', 'falando': 'Falando',
                      'aguardando_seguimento': 'Aguardando seguimento',
                      'cancelado': 'Cancelado', 'erro': 'Erro'}
            label = labels.get(payload.state, payload.state)
            self.voice_status.set(label + ': ' + payload.reason)
            self.hud.set_state(label, payload.reason)
            if payload.state == 'erro':
                self._operation_error = True
        elif kind == "voice_status":
            self.voice_status.set(str(payload))
            status = str(payload).split(': ', 1)[-1] if str(payload).startswith('Whisper ') else str(payload)
            if "Aguardando Jarvis" in str(payload):
                self.hud.set_state("Aguardando Jarvis", "Fallback por transcrição; detector acústico não validado")
            elif status == 'Ouvindo':
                self.hud.set_state('Ouvindo', 'Fala detectada pelo VAD local')
            elif status.startswith('Entendendo'):
                self.hud.set_state('Entendendo', 'Transcrição local em andamento')
            elif status.startswith('Carregando detector'):
                self.hud.set_state('Iniciando', 'Carregando VAD local')
            if "Escuta contínua indisponível:" in str(payload):
                self.voice_listening = False
                self.voice_toggle_button.configure(text="Ativar escuta contínua")
                self.voice_quick.configure(text="Voz: indisponível")
                self.hud.set_state("VOZ INDISPONÍVEL", "Texto continua disponível; confira a entrada de áudio")
        elif kind == "voice_listening":
            self.voice_listening = bool(payload)
            self.voice_quick.configure(text="Voz: ligada" if payload else "Voz: desligada")
            self.voice_toggle_button.configure(
                text="Parar escuta contínua" if self.voice_listening else "Ativar escuta contínua")
        elif kind == 'voice_outputs':
            self.voice_output_choice.configure(values=[''] + list(payload))
        elif kind == 'voice_installed':
            self.voice_piper_model.set(payload)
        elif kind == "voice_test_status":
            self.voice_test_status.set(payload)
        elif kind == "voice_test_error":
            self.voice_level.configure(value=0)
            self.voice_test_status.set("Teste não concluído")
            self._write(self.voice_test_result, str(payload))
            self._write(self.voice_device_result, str(payload))
        elif kind == "voice_test_level":
            self.voice_level.configure(value=max(0, min(100, (payload["dbfs"] + 60) / 60 * 100)))
            self.voice_test_status.set(f"Gravando: {payload['elapsed']:.1f}/6 s · nível {payload['dbfs']:.1f} dBFS")
        elif kind == "voice_capture_level":
            self.voice_capture_level.configure(value=max(0, min(100, (payload["dbfs"] + 60) / 60 * 100)))
            self.voice_status.set(f"Fale agora: {payload['elapsed']:.1f}/6 s · nível {payload['dbfs']:.1f} dBFS")
        elif kind in ("voice_test_probe", "voice_test_capture"):
            text = f"Entrada: {payload['device']}\nFonte PulseAudio: {payload['pulse_source']}\nCaptura: {payload['sample_rate']} Hz, mono\n"
            for warning in payload.get("warnings", []):
                text += "\nAtenção: " + warning
            if kind == "voice_test_capture":
                labels = {"baixo_ou_silencio": "Sinal muito baixo ou silêncio",
                          "possivel_saturacao": "Possível saturação: reduza o volume de entrada",
                          "sinal_detectado": "Sinal detectado; ouça para confirmar a clareza"}
                text += f"\n\n{labels[payload['signal']]}\nNível médio: {payload['metrics']['dbfs']} dBFS"
                text += f"\nAmostras no limite: {payload['metrics']['clipping_percent']}%"
                self.voice_test_status.set("Gravação concluída. Ouça e depois teste a transcrição.")
            else:
                text += "\n\nEntrada compatível. Isso ainda não confirma que sua fala está chegando."
                self.voice_test_status.set("Entrada verificada. Grave uma amostra para medir o sinal.")
            self._write(self.voice_test_result, text)
            self._write(self.voice_device_result, text)
        elif kind == "voice_test_replay":
            self.voice_test_status.set(payload["note"])
        elif kind == "voice_test_transcript":
            text = f"Modelo: {payload['model']} · tempo {payload['seconds']} s (inclui carga inicial)\n\nFrase esperada:\n{payload['expected']}\n\nReconhecido:\n{payload['recognized']}"
            comparison = payload.get("comparison")
            if comparison:
                text += f"\n\nSimilaridade textual: {comparison['similarity_percent']}%"
                text += f"\nEdições por palavra: {comparison['word_edits']} em {comparison['reference_words']} palavras de referência."
            text += "\n\nTeste outro modelo para comparar a MESMA gravação. Isso não mede a precisão geral do Jarvis."
            text += "\n\nPara conversar, abra Conversar, aplique modelo e microfone e diga Jarvis seguido do pedido."
            self._write(self.voice_test_result, text)
            self.voice_test_status.set("Transcrição concluída; confira o texto reconhecido.")
        elif kind == "voice_devices":
            self.devices.configure(values=payload)
        elif kind == "approval_request":
            accepted = messagebox.askyesno("Autorizar operação", payload.action,
                                           parent=self.root)
            self.backend.respond_approval(payload, accepted)

    def _set_capabilities(self, enabled):
        names = sorted(self.backend.service.toolkit.registry.capabilities)
        for child in self.capabilities_frame.winfo_children():
            child.destroy()
        self.capability_vars = {}
        for name in names:
            selected = tk.BooleanVar(value=name in enabled)
            self.capability_vars[name] = selected
            ttk.Checkbutton(self.capabilities_frame, text=name, variable=selected).pack(anchor="w")

    def _close(self):
        self.backend.close()
        self.root.destroy()


def main_gui(config, *, auto=True):
    root = tk.Tk()
    JarvisWindow(root, GuiBackend(config, auto=auto))
    root.mainloop()
