"""ADAM desktop: esfera 3D de partículas em Tkinter Canvas, sem HTML ou servidor web.

Todas as alterações visuais ocorrem na thread Tk. Microfone, FCC, Whisper e TTS
rodam fora da thread da interface. O Canvas reutiliza itens e mede RMS real da
captura única; durante a fala, usa o envelope PCM do WAV enviado ao player.
"""
from __future__ import annotations

import math
import os
from queue import Empty, Queue
import threading
import time
import tkinter as tk
from tkinter import messagebox

from .config import Config


class ParticleSphere(tk.Canvas):
    """Esfera projetada em 2D, com partículas reutilizadas e 30 FPS nominais."""

    def __init__(self, master, *, points=960, fps=30, **kwargs):
        super().__init__(master, bg="#000000", highlightthickness=0, **kwargs)
        self.count = max(200, min(2400, int(points)))
        self.delay = max(16, round(1000 / max(10, min(60, int(fps)))))
        self.state = "parado"
        self.target = 0.
        self.level = 0.
        self.last_level = 0.
        self.rotation = 0.
        self.angular_speed = 0.01
        self.particles = []
        self.items = []
        self.palette = [
            "#101014", "#16161c", "#1f1f25", "#292932",
            "#363640", "#444450", "#575763", "#6c6c79",
            "#858591", "#a2a2ac", "#bdbdc8", "#dedee5", "#ffffff"
        ]
        step = math.pi * (3. - math.sqrt(5.))
        for i in range(self.count):
            y = 1 - (i / (self.count - 1)) * 2
            radius = math.sqrt(max(0, 1 - y * y))
            angle = i * step
            self.particles.append((math.cos(angle) * radius, y, math.sin(angle) * radius, i * .37))
            self.items.append(self.create_oval(-8, -8, -6, -6, fill="#bdbdc8", outline=""))
        self.after(self.delay, self._frame)

    def set_state(self, state):
        self.state = state

    def set_level(self, level):
        self.target = min(1., max(0., float(level)))
        self.last_level = time.monotonic()

    def _frame(self):
        if not self.winfo_exists():
            return
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        cx, cy = w / 2, h / 2
        radius = min(w, h) * .23
        state = self.state
        if time.monotonic() - self.last_level > .24:
            self.target *= .70
        if state in ("pensando", "transcrevendo"):
            goal = max(self.target, .11 + .05 * math.sin(time.monotonic() * 4))
        elif state == "parado":
            goal = .03
        else:
            goal = self.target
        self.level += (goal - self.level) * .20
        target_speed = .026 if state in ("pensando", "transcrevendo") else (.015 if state == "falando" else .008)
        self.angular_speed += (target_speed - self.angular_speed) * .04
        self.rotation += self.angular_speed
        cr, sr = math.cos(self.rotation), math.sin(self.rotation)
        ctilt, stilt = .91, .416
        t = time.monotonic()
        for index, (x, y, z, phase) in enumerate(self.particles):
            wave = 1. + self.level * .4 * math.sin(phase + t * 5 + y * 4)
            xx, yy, zz = x * wave, y * wave, z * wave
            x1 = xx * cr + zz * sr
            z1 = -xx * sr + zz * cr
            y1 = yy * ctilt - z1 * stilt
            z2 = yy * stilt + z1 * ctilt
            depth = max(0., min(1., (z2 + 1.5) / 3.))
            scale = 1.4 / (1.9 - z2 * .5)
            size = .6 + 2.2 * depth
            px, py = cx + x1 * radius * scale, cy + y1 * radius * scale
            point = self.items[index]
            self.coords(point, px - size, py - size, px + size, py + size)
            color = self.palette[min(len(self.palette) - 1, int(depth ** 1.7 * (len(self.palette) - 1)))]
            self.itemconfigure(point, fill=color)
        self.after(self.delay, self._frame)


class AdamWindow:
    def __init__(self, root, config, *, auto=True):
        from .voice import VoiceIO
        from .preferences import PreferenceStore

        self.root, self.config, self.auto = root, config, auto
        self.events = Queue()
        self.jobs = Queue()
        self.voice = VoiceIO()
        # Modelo acústico treinado para Jarvis não é compatível com Adam.
        # Usar fallback por transcrição até existir artefato Adam validado.
        self.voice.wake_manifest = ""
        # A interface ADAM usa exclusivamente o TTS ElevenLabs.
        self.voice.tts_backend = "elevenlabs"
        self.voice.output_meter = lambda level: self.events.put(("output_level", level))
        self.listener = None
        self.controller = None
        self.service = None
        self.turn_lock = threading.Lock()
        self.capture_cancel = threading.Event()
        self.capture_finish = threading.Event()
        self.capturing = threading.Event()
        self.closed = threading.Event()
        self.details = False
        self._last_mic = 0.
        self.active = "parado"
        self.dialog = None

        root.title("ADAM • Assistente Digital Autônomo Modular")
        root.configure(bg="#000000")
        root.minsize(580, 520)
        root.geometry("980x720")
        root.protocol("WM_DELETE_WINDOW", self.close)
        top = tk.Frame(root, bg="#000000")
        top.pack(fill="x", padx=25, pady=(18, 0))
        tk.Label(top, text="A D A M", bg="#000000", fg="#eeeeee",
                 font=("DejaVu Sans", 15, "bold")).pack(side="left")
        self.status = tk.StringVar(value="iniciando · FCC")
        tk.Label(top, textvariable=self.status, bg="#000000", fg="#888891",
                 font=("DejaVu Sans", 10)).pack(side="right")

        self.orb = ParticleSphere(root, points=int(os.getenv("ADAM_PARTICLES", "960")),
                                  fps=int(os.getenv("ADAM_FPS", "30")))
        self.orb.pack(fill="both", expand=True)

        bottom = tk.Frame(root, bg="#000000")
        bottom.pack(fill="x", padx=35, pady=(0, 24))
        self.caption = tk.StringVar(value="")
        self.result = tk.StringVar(value="")
        self.caption_label = tk.Label(bottom, textvariable=self.caption, bg="#000000", fg="#8b8b98",
                                      font=("DejaVu Sans", 11), wraplength=830)
        self.answer_label = tk.Label(bottom, textvariable=self.result, bg="#000000", fg="#e4e4ea",
                                     font=("DejaVu Sans", 15), wraplength=830, justify="center")
        self.caption_label.pack(fill="x", pady=(0, 4))
        self.answer_label.pack(fill="x", pady=(0, 12))
        self.caption_label.pack_forget()
        self.answer_label.pack_forget()
        self.text_frame = tk.Frame(bottom, bg="#000000")
        self.entry = tk.Entry(self.text_frame, bg="#15151a", fg="#f4f4fa",
                              insertbackground="#ffffff", relief="flat",
                              font=("DejaVu Sans", 12), width=60)
        self.entry.pack(fill="x", ipady=9)
        self.entry.bind("<Return>", self._submit_entry)
        self.entry.bind("<Escape>", lambda _: self._toggle_text(False))

        actions = tk.Frame(bottom, bg="#000000")
        actions.pack(pady=(8, 0))
        button = dict(bg="#141419", fg="#ececf3", activebackground="#292931",
                      activeforeground="#ffffff", bd=0, relief="flat", font=("DejaVu Sans", 10),
                      cursor="hand2", padx=14, pady=8)
        self.mic_button = tk.Button(actions, text="Segure para falar", **button)
        self.mic_button.pack(side="left", padx=5)
        self.mic_button.bind("<ButtonPress-1>", self._press)
        self.mic_button.bind("<ButtonRelease-1>", self._release)
        self.listen_button = tk.Button(actions, text="Desativar escuta", command=self.toggle_listen, **button)
        self.listen_button.pack(side="left", padx=5)
        tk.Button(actions, text="Parar", command=self.stop, **button).pack(side="left", padx=5)
        tk.Button(actions, text="⚙", command=self.settings, **button).pack(side="left", padx=5)

        tk.Label(bottom,
                 text="Diga “Adam” · segure ESPAÇO para falar · T digitar · H detalhes · ESC cancelar",
                 bg="#000000", fg="#4e4e5a", font=("DejaVu Sans", 9)).pack(pady=(14, 0))

        root.bind("<KeyPress-space>", self._press)
        root.bind("<KeyRelease-space>", self._release)
        root.bind("<KeyPress-t>", lambda e: self._toggle_text(True))
        root.bind("<KeyPress-h>", self._toggle_details)
        root.bind("<Escape>", lambda _: self.stop())
        self.worker = threading.Thread(target=self._work, daemon=True, name="adam-core")
        self.worker.start()
        self.root.after(70, self._poll)
        if PreferenceStore().load().effective().voice_mode == "continuous":
            self.root.after(150, self.start_listen)
        else:
            self.listen_button.configure(text="Ativar escuta")
        self._state("parado")

    def _state(self, state, description=None):
        self.active = state
        self.orb.set_state(state)
        label = description or {
            "parado": "pronto", "ouvindo": "ouvindo",
            "transcrevendo": "transcrevendo", "pensando": "processando",
            "falando": "falando", "aguardando_ativacao": "aguardando Adam",
        }.get(state, state)
        self.status.set(f"{label} · {self.config.profile.upper()}")

    def _toggle_text(self, on):
        if on:
            self.text_frame.pack(fill="x", pady=(0, 7), before=self.mic_button.master)
            self.entry.focus_set()
        else:
            self.text_frame.pack_forget()
            self.root.focus_set()

    def _toggle_details(self, _event=None):
        self.details = not self.details
        if self.details:
            self.caption_label.pack(fill="x", pady=(0, 4))
            self.answer_label.pack(fill="x", pady=(0, 12))
        else:
            self.caption_label.pack_forget()
            self.answer_label.pack_forget()

    def _submit_entry(self, _event=None):
        value = self.entry.get().strip()
        self.entry.delete(0, "end")
        self._toggle_text(False)
        if value:
            self._enqueue(value)

    def _enqueue(self, message):
        if not self.turn_lock.acquire(blocking=False):
            self.events.put(("error", "ADAM já está atendendo a um pedido. Use Parar para interromper."))
            return False
        self.events.put(("request", str(message)))
        self.jobs.put(("ask", str(message)))
        return True

    def _on_command(self, message):
        return self._enqueue(message)

    def _on_mic_level(self, metrics):
        self.events.put(("mic_level", metrics.get("rms", 0.)))

    def start_listen(self):
        if self.listener is not None or self.closed.is_set():
            return
        from .voice import WakeWordConversation
        self.listener = WakeWordConversation(
            self.voice, self._on_command,
            on_status=lambda status: self.events.put(("listen_status", status)),
            on_level=self._on_mic_level,
        )
        self.listener.start()
        self.listen_button.configure(text="Desativar escuta")
        self._state("aguardando_ativacao", "aguardando Adam")

    def stop_listen(self):
        listener, self.listener = self.listener, None
        if listener is not None:
            listener.stop(timeout=.2)
        self.listen_button.configure(text="Ativar escuta")
        self._state("parado")

    def toggle_listen(self):
        if self.listener is None:
            self.start_listen()
        else:
            self.stop_listen()

    def _press(self, event=None):
        if event is not None and getattr(event, "keysym", "") == "space":
            if self.root.focus_get() == self.entry:
                return
            if getattr(event, "type", None) == "2" and self.capturing.is_set():
                return "break"
        if self.capturing.is_set() or self.turn_lock.locked():
            return "break"
        self.capture_cancel.clear()
        self.capture_finish.clear()
        self.capturing.set()
        threading.Thread(target=self._record, daemon=True, name="adam-record").start()
        self._state("ouvindo")
        return "break"

    def _release(self, _event=None):
        if self.capturing.is_set():
            self.capture_finish.set()
        return "break"

    def _record(self):
        recording = None
        listener = self.listener
        try:
            if listener is not None and not listener.pause(timeout=2.):
                raise RuntimeError("A escuta ainda ocupa o microfone.")
            recording = self.voice.record_turn(
                cancel=self.capture_cancel,
                finish=self.capture_finish,
                on_level=self._on_mic_level,
            )
            self.events.put(("phase", "transcrevendo"))
            message = self.voice.transcribe(recording)
            if not self.capture_cancel.is_set() and not self.closed.is_set():
                self._enqueue(message)
        except Exception as exc:
            if not self.capture_cancel.is_set():
                self.events.put(("error", str(exc)))
        finally:
            if recording is not None:
                recording.unlink(missing_ok=True)
            self.capturing.clear()
            if listener is not None and not self.turn_lock.locked():
                listener.resume()
            if not self.turn_lock.locked():
                self.events.put(("phase", "parado"))

    def _work(self):
        while True:
            kind, value = self.jobs.get()
            if kind == "shutdown":
                if self.service is not None:
                    try:
                        self.service.close()
                    except RuntimeError:
                        pass
                return
            try:
                if self.service is None:
                    from .service import JarvisService
                    self.service = JarvisService.from_config(
                        self.config, auto=self.auto,
                        report=lambda message: self.events.put(("progress", str(message))),
                    )
                if kind == "model":
                    if self.turn_lock.locked():
                        raise RuntimeError("Não altere modelo durante uma tarefa.")
                    self.service.client.select_model(value)
                    self.service.agent.model = self.service.client.active_model
                    self.events.put(("model", self.service.client.active_model))
                    continue
                from .conversation import ConversationController
                self.controller = ConversationController(
                    self.service,
                    emit=lambda event: self.events.put(("phase", event.state)),
                )
                self.controller.run(
                    value, voice=self.voice, on_text=lambda delta: self.events.put(("delta", delta)),
                    display=lambda answer: self.events.put(("answer", answer)),
                )
            except Exception as exc:
                self.events.put(("error", str(exc)[:350]))
            finally:
                self.controller = None
                if kind == "ask":
                    if self.turn_lock.locked():
                        self.turn_lock.release()
                    if self.listener is not None:
                        self.listener.resume()
                self.events.put(("phase", "parado"))

    def _poll(self):
        if self.closed.is_set():
            return
        for _ in range(80):
            try:
                kind, value = self.events.get_nowait()
            except Empty:
                break
            if kind == "request":
                self.caption.set("Você: " + value)
                self.result.set("")
                self._state("pensando")
            elif kind == "delta":
                self.result.set((self.result.get() + value)[-1600:])
            elif kind == "answer":
                self.result.set(value[-1600:])
            elif kind == "phase":
                if value == "executando":
                    self._state("pensando")
                elif value in ("falando", "ouvindo", "transcrevendo", "parado"):
                    self._state(value)
            elif kind == "mic_level":
                self.orb.set_level(min(1., float(value) * 14))
            elif kind == "output_level":
                self.orb.set_level(value)
            elif kind == "listen_status":
                if "indisponível" in value or "Falha" in value or "Descartado" in value:
                    self._state("parado", value[:86])
                elif "Aguardando Adam" in value:
                    self._state("aguardando_ativacao")
            elif kind == "error":
                self._state("parado", "erro: " + value[:80])
            elif kind == "progress":
                if self.details:
                    self.status.set(value[:85])
            elif kind == "model":
                self.status.set("modelo: " + value)
        self.root.after(45, self._poll)

    def stop(self):
        self.capture_cancel.set()
        self.capture_finish.set()
        self.voice.cancel_speech()
        if self.controller is not None:
            self.controller.cancel()
        elif self.service is not None:
            self.service.cancel_current()
        self.events.put(("phase", "parado"))

    def settings(self):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.lift()
            return
        dialog = tk.Toplevel(self.root)
        self.dialog = dialog
        dialog.configure(bg="#101015")
        dialog.title("ADAM · Configurações")
        dialog.resizable(False, False)
        dialog.geometry("490x280")
        f = tk.Frame(dialog, bg="#101015", padx=25, pady=20)
        f.pack(fill="both", expand=True)
        tk.Label(f, text="Modelo de conversa (FCC)", bg="#101015", fg="#eeeeee",
                 font=("DejaVu Sans", 12, "bold")).pack(anchor="w")
        model = tk.Entry(f, bg="#24242d", fg="#fff", relief="flat", insertbackground="#fff", width=50)
        model.insert(0, self.config.model)
        model.pack(fill="x", ipady=9, pady=(8, 14))
        tk.Label(f, text="Voz: ElevenLabs · ID e chave pelas variáveis de ambiente.\n"
                         "Ollama local permanece como opção separada, não exigida pelo FCC.",
                 bg="#101015", fg="#9999a4", justify="left", wraplength=440).pack(anchor="w")
        def save():
            model_id = model.get().strip()
            if not model_id or self.turn_lock.locked():
                messagebox.showwarning("ADAM", "Informe um modelo ou finalize o pedido.", parent=dialog)
                return
            self.jobs.put(("model", model_id))
            dialog.destroy()
        tk.Button(f, text="Aplicar modelo", command=save, bg="#353543", fg="#fff",
                  relief="flat", padx=12, pady=8).pack(anchor="e", pady=(12, 0))

    def close(self):
        self.closed.set()
        self.stop()
        if self.listener is not None:
            self.listener.stop(timeout=.2)
        self.jobs.put(("shutdown", None))
        self.root.destroy()


def main_gui(config=None, *, auto=True):
    config = config or Config.from_env()
    root = tk.Tk()
    AdamWindow(root, config, auto=auto)
    root.mainloop()


def launch():
    main_gui()
