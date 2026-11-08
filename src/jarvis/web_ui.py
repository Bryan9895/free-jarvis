"""Web UI da esfera do Jarvis: usa o JarvisService existente, sem Claude Code.

A página original de Matheus Tilli é distribuída sob licença MIT.
O servidor atende SOMENTE loopback e não expõe a chave ElevenLabs ao navegador.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from queue import Empty, Full, Queue
import shutil
import subprocess
import tempfile
from threading import Event, Lock, Thread
from time import monotonic
from uuid import uuid4
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .config import Config
from .speech_text import SentenceBuffer, spoken_text

WEB = Path(__file__).with_name("web")
MAX_AUDIO = 16 * 1024 * 1024
MAX_TEXT = 16 * 1024
SAMPLE = "Às suas ordens. Como posso ajudar?"


class OrbState:
    """Um worker possui o serviço e a conexão SQLite; requisições HTTP só enfileiram."""

    def __init__(self, config, *, start_worker=True):
        self.config = config
        self.clients = set()
        self.clients_lock = Lock()
        self.turn_lock = Lock()
        self.busy = Event()
        self.generation = 0
        self.service = None
        self.jobs = Queue()
        self.last_error = ""
        self.tts = {}
        self.tts_lock = Lock()
        self.voices = json.loads((WEB / "vozes.json").read_text(encoding="utf-8"))
        self.prefs_file = Path(os.getenv("JARVIS_ORB_SETTINGS", "~/.config/jarvis-fcc/orb-ui.json")).expanduser()
        self.voice_id = os.getenv("JARVIS_VOZ", "xHUwLsLfyqiYOIVTzLRW")
        self.speed = 1.0
        try:
            saved = json.loads(self.prefs_file.read_text(encoding="utf-8"))
            if saved.get("voz") in {v["id"] for v in self.voices}:
                self.voice_id = saved["voz"]
            speed = float(saved.get("velocidade", 1.0))
            if 0.7 <= speed <= 1.2:
                self.speed = speed
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        from .voice import VoiceIO
        self.voice = VoiceIO()
        self.eleven_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        self.tts_model = os.getenv("JARVIS_MODELO_VOZ", "eleven_flash_v2_5")
        self.worker = None
        if start_worker:
            self.worker = Thread(target=self._run, name="jarvis-orb-core", daemon=True)
            self.worker.start()

    def emit(self, event):
        with self.clients_lock:
            watchers = tuple(self.clients)
        for listener in watchers:
            try:
                listener.put_nowait(event)
            except Full:
                # Não bloquear o modelo por um cliente desconectado ou lento.
                try:
                    listener.get_nowait()
                    listener.put_nowait(event)
                except (Empty, Full):
                    pass

    def subscribe(self):
        listener = Queue(maxsize=100)
        with self.clients_lock:
            self.clients.add(listener)
        listener.put({"tipo": "estado", "estado": "pensando" if self.busy.is_set() else "parado"})
        if self.last_error:
            listener.put({"tipo": "aviso", "texto": self.last_error[:250]})
        return listener

    def unsubscribe(self, listener):
        with self.clients_lock:
            self.clients.discard(listener)

    def _current(self, generation):
        with self.turn_lock:
            return generation == self.generation

    def submit(self, *, text=None, audio=None, mime="audio/webm"):
        with self.turn_lock:
            if self.busy.is_set():
                return False
            self.busy.set()
            generation = self.generation
        self.jobs.put((generation, text, audio, mime))
        return True

    def cancel(self):
        with self.turn_lock:
            self.generation += 1
        self.voice.cancel_speech()
        if self.service is not None:
            self.service.cancel_current()
        self.emit({"tipo": "estado", "estado": "parado"})

    def reset(self):
        # Reinicia a sessão visível, mas preserva o SQLite e as autorizações.
        self.cancel()
        self.emit({"tipo": "aviso", "texto": "Conversa visual reiniciada; memória local preservada."})

    def _transcribe(self, audio, mime):
        if not shutil.which("ffmpeg"):
            raise RuntimeError("Instale ffmpeg para transcrever áudio do navegador.")
        suffix = ".webm" if "webm" in mime else ".ogg" if "ogg" in mime else ".mp4"
        with tempfile.TemporaryDirectory(prefix="jarvis-orb-") as directory:
            source = Path(directory) / ("entrada" + suffix)
            wav = Path(directory) / "fala.wav"
            source.write_bytes(audio)
            result = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i",
                 str(source), "-ac", "1", "-ar", "16000", str(wav)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=40, check=False,
            )
            if result.returncode or not wav.is_file():
                raise RuntimeError("Não consegui converter a gravação. Verifique o áudio do navegador.")
            return self.voice.transcribe(wav, beam_size=1)

    def _voice_available(self):
        if self.eleven_key:
            return True
        return (self.voice.tts_backend == "kokoro" or
                (self.voice.piper_model is not None and self.voice.piper_model.is_file()))

    def _audio_url(self, text, *, voice_id=None):
        text = spoken_text(text).strip()
        if not text or not self._voice_available():
            return ""
        audio_id = uuid4().hex
        with self.tts_lock:
            if len(self.tts) >= 96:
                # Cache efêmero: nunca manter áudio/transcrição persistente por padrão.
                self.tts.pop(next(iter(self.tts)))
            self.tts[audio_id] = (text[:3000], voice_id or self.voice_id, self.speed)
        return "/api/voz/" + audio_id

    def render_audio(self, audio_id):
        with self.tts_lock:
            item = self.tts.get(audio_id)
        if item is None:
            raise KeyError("Áudio expirado")
        text, voice_id, speed = item
        if self.eleven_key:
            if voice_id not in {v["id"] for v in self.voices}:
                raise ValueError("Voz inválida")
            body = json.dumps({
                "text": text, "model_id": self.tts_model,
                "voice_settings": {"speed": speed},
            }).encode("utf-8")
            request = Request(
                "https://api.elevenlabs.io/v1/text-to-speech/" + voice_id + "/stream",
                data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "xi-api-key": self.eleven_key,
                         "Accept": "audio/mpeg"},
            )
            with urlopen(request, timeout=45) as response:
                audio = response.read(8 * 1024 * 1024 + 1)
            if len(audio) > 8 * 1024 * 1024:
                raise ValueError("Resposta de áudio maior que o permitido")
            return audio, "audio/mpeg"
        from .tts_engine import synthesize_for
        fd, path = tempfile.mkstemp(prefix="jarvis-orb-tts-", suffix=".wav")
        os.close(fd)
        try:
            self.voice.prepare_speech()
            synthesize_for(self.voice, text, Path(path), self.voice._speech_cancel)
            return Path(path).read_bytes(), "audio/wav"
        finally:
            Path(path).unlink(missing_ok=True)

    def preview(self, voice_id):
        if voice_id not in {v["id"] for v in self.voices}:
            raise ValueError("Voz inválida")
        url = self._audio_url(SAMPLE, voice_id=voice_id)
        if not url:
            raise RuntimeError("Configure ELEVENLABS_API_KEY ou uma voz local.")
        return self.render_audio(url.rsplit("/", 1)[-1])

    def config_view(self):
        return {"voz": self.voice_id, "velocidade": self.speed, "vozes": self.voices}

    def save_config(self, changes):
        if "voz" in changes:
            if changes["voz"] not in {v["id"] for v in self.voices}:
                raise ValueError("Voz inválida")
            self.voice_id = changes["voz"]
        if "velocidade" in changes:
            speed = float(changes["velocidade"])
            if not 0.7 <= speed <= 1.2:
                raise ValueError("Velocidade fora do intervalo")
            self.speed = round(speed, 2)
        self.prefs_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".orb-", dir=self.prefs_file.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"voz": self.voice_id, "velocidade": self.speed},
                          handle, ensure_ascii=False)
            os.replace(tmp, self.prefs_file)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return self.config_view()

    def _run(self):
        while True:
            generation, text, audio, mime = self.jobs.get()
            start = monotonic()
            heard = ""
            try:
                if not self._current(generation):
                    continue
                if audio is not None:
                    self.emit({"tipo": "estado", "estado": "transcrevendo"})
                    heard = self._transcribe(audio, mime)
                else:
                    heard = str(text or "").strip()
                if not self._current(generation):
                    continue
                if not heard:
                    self.emit({"tipo": "aviso", "texto": "Não reconheci nenhuma fala."})
                    continue
                self.emit({"tipo": "voce", "texto": heard})
                self.emit({"tipo": "estado", "estado": "pensando"})
                if self.service is None:
                    from .service import JarvisService
                    self.service = JarvisService.from_config(
                        self.config, auto=True,
                        report=lambda message: self.emit({"tipo": "ferramenta",
                                                           "rotulo": str(message)[:90]}),
                    )
                buffer = SentenceBuffer()
                spoken_any = False
                def text_delta(delta):
                    nonlocal spoken_any
                    if not self._current(generation):
                        return
                    for phrase in buffer.feed(delta):
                        url = self._audio_url(phrase)
                        if url:
                            spoken_any = True
                            self.emit({"tipo": "fala", "audio": url})
                answer = self.service.ask_stream(heard, on_text=text_delta)
                if not self._current(generation):
                    continue
                leftover = " ".join(buffer.finish())
                final_audio = self._audio_url(leftover if spoken_any else answer)
                self.emit({
                    "tipo": "resposta", "texto": answer,
                    "audio": final_audio, "segundos": round(monotonic() - start, 2),
                })
                self.last_error = ""
            except Exception as exc:
                if self._current(generation):
                    self.last_error = str(exc)
                    self.emit({"tipo": "aviso", "texto": "Falha: " + str(exc)[:180]})
            finally:
                self.busy.clear()
                self.emit({"tipo": "estado", "estado": "parado"})


class OrbHandler(BaseHTTPRequestHandler):
    """API compatível com web/index.html da referência; acesso estritamente local."""

    server_version = "JarvisOrb/1.0"

    @property
    def app(self):
        return self.server.app

    def log_message(self, format, *args):
        pass

    def _allowed(self):
        host = self.headers.get("Host", "").split(":")[0].lower()
        if host not in ("127.0.0.1", "localhost"):
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            return (parsed.scheme == "http" and parsed.hostname == host and
                    parsed.port == self.server.server_port)
        return True

    def _send(self, status, body=b"", content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; connect-src 'self'; media-src 'self'; img-src 'self' data:")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status, data):
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _read(self, cap):
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            raise ValueError("Comprimento de requisição inválido")
        if not 0 <= length <= cap:
            raise ValueError("Requisição excede o limite permitido")
        return self.rfile.read(length)

    def do_GET(self):
        if not self._allowed():
            return self._json(403, {"erro": "Acesso não permitido"})
        path = self.path.split("?", 1)[0]
        if path == "/api/eventos":
            return self._events()
        if path == "/api/config":
            return self._json(200, self.app.config_view())
        if path == "/api/saude":
            return self._json(200, {"servico": "orb", "ocupado": self.app.busy.is_set(),
                                    "perfil": self.app.config.profile})
        if path.startswith("/api/voz/") or path.startswith("/api/amostra/"):
            try:
                if path.startswith("/api/voz/"):
                    audio, mime = self.app.render_audio(path.rsplit("/", 1)[-1])
                else:
                    audio, mime = self.app.preview(path.rsplit("/", 1)[-1])
                return self._send(200, audio, mime)
            except (KeyError, ValueError, RuntimeError) as exc:
                return self._json(404, {"erro": str(exc)})
            except Exception:
                return self._json(502, {"erro": "Serviço de síntese indisponível"})
        if path == "/":
            return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
        self._json(404, {"erro": "Rota inexistente"})

    def do_POST(self):
        if not self._allowed():
            return self._json(403, {"erro": "Origem não autorizada"})
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/interromper":
                self.app.cancel()
                return self._json(200, {"interrompeu": True})
            if path == "/api/reiniciar":
                self.app.reset()
                return self._json(200, {"ok": True})
            if path == "/api/diag":
                self._read(MAX_TEXT)
                return self._json(200, {"ok": True})
            if path == "/api/config":
                data = json.loads(self._read(MAX_TEXT))
                if not isinstance(data, dict):
                    raise ValueError("Configuração inválida")
                return self._json(200, self.app.save_config(data))
            if path == "/api/texto":
                data = json.loads(self._read(MAX_TEXT))
                text = data.get("texto", "") if isinstance(data, dict) else ""
                if not isinstance(text, str) or len(text) > 8000:
                    raise ValueError("Texto inválido")
                return self._json(202 if self.app.submit(text=text) else 409, {"ok": True})
            if path == "/api/audio":
                audio = self._read(MAX_AUDIO)
                if len(audio) < 2000:
                    return self._json(400, {"erro": "Áudio vazio"})
                mime = self.headers.get("Content-Type", "audio/webm")
                if not mime.startswith(("audio/webm", "audio/ogg", "audio/mp4")):
                    raise ValueError("Formato de áudio incompatível")
                return self._json(202 if self.app.submit(audio=audio, mime=mime) else 409,
                                  {"ok": True})
            return self._json(404, {"erro": "Rota inexistente"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.app.emit({"tipo": "aviso", "texto": str(exc)[:180]})
            self.app.emit({"tipo": "estado", "estado": "parado"})
            self._json(400, {"erro": str(exc)[:180]})

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        listener = self.app.subscribe()
        try:
            while True:
                try:
                    event = listener.get(timeout=15)
                    data = "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                except Empty:
                    data = ": ping\n\n"
                self.wfile.write(data.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            self.app.unsubscribe(listener)


def serve(config, *, port=None, open_browser=True):
    port = int(os.getenv("JARVIS_UI_PORT", "8790") if port is None else port)
    if not 1 <= port <= 65535:
        raise ValueError("JARVIS_UI_PORT deve ser uma porta TCP válida")
    app = OrbState(config)
    server = ThreadingHTTPServer(("127.0.0.1", port), OrbHandler)
    server.app = app
    url = "http://127.0.0.1:" + str(server.server_port)
    print("JARVIS · Esfera: " + url, flush=True)
    print("Atalhos: Espaço = segurar para falar; T = digitar; H = detalhes; N = limpar tela.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.cancel()
        server.server_close()


def launch():
    serve(Config.from_env())
