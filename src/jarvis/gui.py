"""Interface Tkinter leve sobre JarvisService; FCC e SQLite rodam em worker."""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, scrolledtext, ttk

from .service import JarvisService


@dataclass
class ApprovalRequest:
    action: str
    event: threading.Event = field(default_factory=threading.Event)
    accepted: bool = False


class GuiBackend:
    """Fila de comandos para manter GUI responsiva e conexões SQLite na mesma thread."""

    def __init__(self, config, *, auto=True, service_factory=None):
        self.config = config
        self.auto = auto
        self.service_factory = service_factory or JarvisService.from_config
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.service = None
        self._approval = None
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-gui-worker")

    def start(self):
        self._thread.start()

    def submit(self, command, value=None):
        self.commands.put((command, value))

    def cancel(self):
        service = self.service
        cancelled = service.cancel_current() if service is not None else False
        request = self._approval
        if request is not None:
            request.accepted = False
            request.event.set()
        return cancelled

    def revoke(self):
        service = self.service
        if service is not None:
            service.approval.revoke()
            self.cancel()
            self.events.put(("approval_mode", "revoked"))

    def close(self):
        self._closed.set()
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
                if command == "retry":
                    if self.service is None:
                        try:
                            self._connect()
                        except Exception as exc:
                            self.events.put(("connection_error", str(exc)))
                    continue
                if self.service is None:
                    self.events.put(("error", "Conecte ao FCC antes de executar uma tarefa."))
                    continue
                try:
                    self._dispatch(command, value)
                except Exception as exc:
                    self.events.put(("error", str(exc)))
        finally:
            if self.service is not None:
                try:
                    self.service.close()
                except RuntimeError:
                    pass
            self.events.put(("closed", None))

    def _dispatch(self, command, value):
        service = self.service
        if command == "ask":
            self.events.put(("busy", True))
            try:
                answer = service.ask(value)
                self.events.put(("answer", answer))
                self.events.put(("metrics", service.agent.last_metrics))
                self.events.put(("plan", service.planner.snapshot()))
            finally:
                self.events.put(("busy", False))
        elif command == "snapshot":
            self.events.put(("plan", service.planner.snapshot()))
        elif command == "models":
            self.events.put(("models", service.client.available_models()))
        elif command == "select_model":
            service.client.select_model(value)
            service.agent.model = value
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
            device = int(value.split(":", 1)[0]) if value else None
            voice = VoiceIO(device=device)
            self.events.put(("transcript", voice.listen_once(6)))
        elif command == "voice_devices":
            from .voice import VoiceIO
            self.events.put(("voice_devices", [f"{index}: {name}"
                                             for index, name in VoiceIO.input_devices()]))
        elif command == "voice_speak":
            from .voice import VoiceIO
            from os import getenv
            voice = VoiceIO(piper_model=getenv("JARVIS_PIPER_MODEL", ""))
            self.events.put(("voice_status", voice.speak(value)))


class JarvisWindow:
    def __init__(self, root, backend: GuiBackend):
        self.root, self.backend = root, backend
        self.last_answer = ""
        root.title("JARVIS FCC")
        root.geometry("1050x680")
        root.minsize(760, 480)
        self.connection = tk.StringVar(value="Conectando ao FCC…")
        self.model = tk.StringVar()
        self.approval_mode = tk.StringVar(value="auto")
        self.voice_device = tk.StringVar()
        self.capability_vars = {}
        self._build()
        root.protocol("WM_DELETE_WINDOW", self._close)
        self.backend.start()
        root.after(100, self._poll)

    def _build(self):
        header = ttk.Frame(self.root, padding=8)
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.connection).pack(side="left", padx=4)
        ttk.Button(header, text="Reconectar", command=lambda: self.backend.submit("retry")).pack(side="left")
        ttk.Label(header, text="Modelo:").pack(side="left", padx=(18, 4))
        self.models = ttk.Combobox(header, textvariable=self.model, width=30)
        self.models.pack(side="left")
        ttk.Button(header, text="Listar", command=lambda: self.backend.submit("models")).pack(side="left")
        ttk.Button(header, text="Selecionar", command=lambda: self.backend.submit(
            "select_model", self.model.get())).pack(side="left")

        split = ttk.PanedWindow(self.root, orient="horizontal")
        split.pack(fill="both", expand=True, padx=8, pady=4)
        conversation = ttk.Frame(split)
        tabs = ttk.Notebook(split)
        split.add(conversation, weight=3)
        split.add(tabs, weight=2)

        self.chat = scrolledtext.ScrolledText(conversation, wrap="word", state="disabled")
        self.chat.pack(fill="both", expand=True)
        send = ttk.Frame(conversation)
        send.pack(fill="x", pady=6)
        self.message = ttk.Entry(send)
        self.message.pack(side="left", fill="x", expand=True)
        self.message.bind("<Return>", lambda _event: self._send())
        self.send_button = ttk.Button(send, text="Enviar", command=self._send)
        self.send_button.pack(side="left", padx=3)
        ttk.Button(send, text="🎙 Gravar", command=lambda: self.backend.submit(
            "voice_record", self.voice_device.get())).pack(side="left")
        ttk.Button(send, text="Ler", command=lambda: self.backend.submit(
            "voice_speak", self.last_answer)).pack(side="left")
        ttk.Button(send, text="Cancelar", command=self._cancel).pack(side="left")

        tasks = ttk.Frame(tabs, padding=8)
        tabs.add(tasks, text="Tarefa")
        self.plan_status = tk.StringVar(value="Sem plano")
        ttk.Label(tasks, textvariable=self.plan_status).pack(anchor="w")
        self.steps = ttk.Treeview(tasks, columns=("id", "status", "description"), show="headings")
        for key, title, width in (("id", "#", 35), ("status", "Estado", 110),
                                  ("description", "Etapa", 260)):
            self.steps.heading(key, text=title)
            self.steps.column(key, width=width)
        self.steps.pack(fill="both", expand=True)
        ttk.Button(tasks, text="Atualizar", command=lambda: self.backend.submit("snapshot")).pack()

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
        self.history = scrolledtext.ScrolledText(history, wrap="word", state="disabled")
        self.history.pack(fill="both", expand=True)
        ttk.Button(history, text="Atualizar", command=lambda: self.backend.submit("history")).pack()

        metrics = ttk.Frame(tabs, padding=8)
        tabs.add(metrics, text="Métricas")
        self.metrics = scrolledtext.ScrolledText(metrics, wrap="word", state="disabled")
        self.metrics.pack(fill="both", expand=True)

        voice = ttk.Frame(tabs, padding=8)
        tabs.add(voice, text="Voz")
        ttk.Label(voice, text="Microfone; transcrição pode ser corrigida antes de enviar").pack(anchor="w")
        self.devices = ttk.Combobox(voice, textvariable=self.voice_device, width=40)
        self.devices.pack(fill="x", pady=5)
        ttk.Button(voice, text="Listar microfones", command=lambda: self.backend.submit(
            "voice_devices")).pack(fill="x")
        ttk.Button(voice, text="Gravar 6 segundos", command=lambda: self.backend.submit(
            "voice_record", self.voice_device.get())).pack(fill="x")

    def _write(self, widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", value)
        widget.configure(state="disabled")

    def _append_chat(self, label, value):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{label}: {value}\n\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _send(self):
        message = self.message.get().strip()
        if message:
            self.message.delete(0, "end")
            self._append_chat("Você", message)
            self.backend.submit("ask", message)

    def _cancel(self):
        if self.backend.cancel():
            self._append_chat("Sistema", "Cancelamento solicitado; aguardando a chamada atual terminar.")

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
        try:
            while True:
                kind, payload = self.backend.events.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._poll)

    def _handle(self, kind, payload):
        if kind == "connected":
            self.connection.set("Catálogo FCC acessível; inferência ainda não testada")
            self.model.set(payload["model"])
            self.approval_mode.set(payload["approval"])
            self._set_capabilities(payload["capabilities"])
            self.backend.submit("snapshot")
        elif kind == "connection_error":
            self.connection.set("FCC indisponível")
            self._append_chat("Sistema", payload)
        elif kind == "answer":
            self.last_answer = payload
            self._append_chat("JARVIS", payload)
        elif kind == "error":
            self._append_chat("Erro", payload)
        elif kind == "progress":
            self._append_chat("Etapa", payload)
        elif kind == "busy":
            self.send_button.configure(state="disabled" if payload else "normal")
        elif kind == "metrics":
            self._write(self.metrics, json.dumps(payload, ensure_ascii=False, indent=2))
        elif kind == "plan":
            self.plan_status.set(f"Plano: {payload.get('status', 'desconhecido')}")
            self.steps.delete(*self.steps.get_children())
            for step in payload.get("steps", []):
                self.steps.insert("", "end", values=(step.get("id"), step.get("status"),
                                                     step.get("description")))
        elif kind == "models":
            self.models.configure(values=payload)
        elif kind == "model":
            self.model.set(payload)
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
        elif kind == "voice_status":
            self._append_chat("Voz", str(payload))
        elif kind == "voice_devices":
            self.devices.configure(values=payload)
            if payload and not self.voice_device.get():
                self.voice_device.set(payload[0])
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
