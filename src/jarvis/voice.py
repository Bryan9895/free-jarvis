"""Camada de voz local e opcional: SoundDevice -> faster-whisper -> Piper."""
from __future__ import annotations
import os
from collections import deque
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from array import array
from math import sqrt

class VoiceError(RuntimeError):
    """Falha recuperável de áudio."""

class VoiceIO:
    def __init__(self, model="tiny", language="pt", piper_model="", sample_rate=16000,
                 device=None, silence_rms=150):
        self.model_name = model
        self.language = language
        self.piper_model = Path(piper_model).expanduser() if piper_model else None
        self.sample_rate = sample_rate
        self.device = device if device is not None else os.getenv("JARVIS_AUDIO_DEVICE")
        self.silence_rms = silence_rms
        self._stt = None

    @staticmethod
    def input_devices():
        try:
            import sounddevice as sd
            return [(index, item["name"]) for index, item in enumerate(sd.query_devices())
                    if item.get("max_input_channels", 0) > 0]
        except ImportError as exc:
            raise VoiceError("Instale: pip install -e '.[voice]'") from exc
        except Exception as exc:
            raise VoiceError(f"Não foi possível listar microfones: {exc}") from exc

    def record(self, seconds=6, *, allow_silence=False, on_level=None):
        """Grava WAV PCM16 temporário; o chamador deve apagar o arquivo."""
        if not 1 <= seconds <= 15:
            raise VoiceError("A gravação deve durar entre 1 e 15 segundos")
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise VoiceError("Instale: pip install -e '.[voice]'") from exc
        try:
            chunks = []
            completed = threading.Event()
            remaining = int(self.sample_rate * seconds)

            def receive(indata, _count, _timing, _status):
                nonlocal remaining
                take = min(remaining, len(indata))
                if take:
                    chunk = indata[:take].tobytes()
                    chunks.append(chunk)
                    remaining -= take
                    if on_level is not None:
                        from .voice_diagnostics import signal_metrics
                        on_level({**signal_metrics(chunk),
                                  "elapsed": round(seconds-remaining/self.sample_rate, 1)})
                if remaining == 0:
                    completed.set()
                    raise sd.CallbackStop

            stream = sd.InputStream(samplerate=self.sample_rate, channels=1,
                                    dtype="int16", device=self.device, callback=receive,
                                    blocksize=max(1, self.sample_rate // 10))
            try:
                stream.start()
                if not completed.wait(seconds + 3):
                    raise VoiceError("Tempo limite de captura: o dispositivo não entregou áudio. "
                                     "Confira o microfone selecionado e evite entradas monitor/loopback.")
                audio_bytes = b"".join(chunks)
            finally:
                try:
                    stream.abort()
                finally:
                    stream.close()
            frames = array("h")
            frames.frombytes(audio_bytes)
            if not allow_silence and (not frames or sqrt(
                    sum(sample * sample for sample in frames) / len(frames)) < self.silence_rms):
                raise VoiceError("Nenhuma fala detectada; gravação descartada")
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceError(f"Microfone indisponível: {exc}") from exc
        fd, location = tempfile.mkstemp(prefix="jarvis_mic_", suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as raw:
                with wave.open(raw, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(self.sample_rate)
                    wav.writeframes(audio_bytes)
            return Path(location)
        except BaseException:
            Path(location).unlink(missing_ok=True)
            raise

    def transcribe(self, filename):
        filename = Path(filename)
        if not filename.is_file():
            raise VoiceError("Arquivo de gravação inexistente")
        try:
            if self._stt is None:
                from faster_whisper import WhisperModel
                self._stt = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            segments, _ = self._stt.transcribe(str(filename), language=self.language,
                                                vad_filter=True, beam_size=5,
                                                condition_on_previous_text=False)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            if not text:
                raise VoiceError("Nenhuma fala reconhecida")
            return text
        except VoiceError:
            raise
        except ImportError as exc:
            raise VoiceError("Instale: pip install -e '.[voice]'") from exc
        except Exception as exc:
            raise VoiceError(f"Falha na transcrição: {exc}") from exc

    def speak(self, text):
        """Piper sintetiza localmente. Sem configuração, não envia fala para nuvem."""
        if not text.strip():
            return "empty"
        if self.piper_model is None:
            return "disabled"
        if not self.piper_model.is_file():
            raise VoiceError("Modelo de voz Piper não encontrado em JARVIS_PIPER_MODEL")
        if not shutil.which("piper"):
            raise VoiceError("Executável 'piper' não está no PATH")
        if not shutil.which("aplay"):
            raise VoiceError("Instale 'alsa-utils' para executar aplay")
        fd, location = tempfile.mkstemp(prefix="jarvis_speech_", suffix=".wav")
        os.close(fd)
        wav_path = Path(location)
        try:
            synth = subprocess.run(
                ["piper", "--model", str(self.piper_model), "--output_file", str(wav_path)],
                input=text[:3000], text=True, capture_output=True, timeout=90, check=False,
            )
            if synth.returncode != 0:
                raise VoiceError("Falha no Piper: " + synth.stderr[-500:])
            output = subprocess.run(["aplay", "-q", str(wav_path)], capture_output=True,
                                    timeout=90, check=False)
            if output.returncode != 0:
                raise VoiceError("Não foi possível reproduzir o áudio")
            return "spoken"
        except subprocess.TimeoutExpired as exc:
            raise VoiceError("Tempo limite de síntese/reprodução excedido") from exc
        finally:
            wav_path.unlink(missing_ok=True)

    def listen_once(self, seconds=6):
        recording = self.record(seconds)
        try:
            return self.transcribe(recording)
        finally:
            recording.unlink(missing_ok=True)


class WakeWordConversation:
    """Escuta a frase de ativação localmente e entrega uma fala por vez."""

    FRAME_SAMPLES = 1280  # Blocos de 80 ms para detecção de atividade de voz.
    WAKE_PATTERN = re.compile(
        r"^\s*(?:(?:hey|ei)\s+)?(?:d?jarv(?:is|es|ez)|dav(?:i|ie)s|de\s+avis|a\s+visa)\b[\s,.:;!?-]*",
        re.IGNORECASE,
    )

    STOP_PHRASES = {"parar conversa", "pare conversa", "encerrar conversa",
                    "voltar a espera", "pare de ouvir"}

    def __init__(self, voice: VoiceIO, on_command, on_status=lambda _message: None,
                 *, device=None, silence_seconds=1.0,
                 max_command_seconds=15, on_transcript=lambda _text: None):
        self.voice = voice
        self.on_command = on_command
        self.on_status = on_status
        self.on_transcript = on_transcript
        self.device = voice.device if device is None else device
        self.silence_seconds = silence_seconds
        self.max_command_seconds = max_command_seconds
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._thread = None
        self._capture_guard = threading.Lock()
        self._capture_idle = threading.Event()
        self._capture_idle.set()

    @classmethod
    def remove_wake_word(cls, text):
        return cls.WAKE_PATTERN.sub("", text, count=1).strip()

    @classmethod
    def extract_wake_command(cls, text):
        match = cls.WAKE_PATTERN.match(text)
        return (True, text[match.end():].strip()) if match else (False, text.strip())

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._resume.set()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="jarvis-wakeword-listener")
        self._thread.start()

    def stop(self, timeout=2):
        self._stop.set()
        self._resume.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=timeout)
        return self._thread is None or not self._thread.is_alive()

    def pause(self, timeout=0):
        with self._capture_guard:
            self._resume.clear()
        return self._capture_idle.wait(timeout)

    def resume(self):
        self._resume.set()

    def _run(self):
        try:
            try:
                import numpy as np
                import sounddevice as sd
            except ImportError as exc:
                raise VoiceError(
                    "Escuta contínua requer os pacotes do extra 'voice'."
                ) from exc

            self.on_status("Aguardando Jarvis; detecção e transcrição são locais…")
            conversation = False
            while not self._stop.is_set():
                if not self._resume.wait(0.2):
                    continue
                woke = not conversation
                samples = self._listen_for_command(
                    sd, np, idle_timeout=20 if conversation else None)
                if self._stop.is_set():
                    break
                if not self._resume.is_set():
                    continue
                if samples is None:
                    conversation = False
                    self.on_status("Conversa pausada. Diga Jarvis para iniciar outra.")
                    continue
                self.on_status("Verificando fala e palavra de ativação localmente…")
                recording = self._write_recording(samples)
                try:
                    transcript = self.voice.transcribe(recording)
                    self.on_transcript(transcript)
                    if woke:
                        activated, transcript = self.extract_wake_command(transcript)
                        if not activated:
                            self.on_status("Fala reconhecida, mas sem ativação. Comece o pedido com Jarvis.")
                            continue
                    else:
                        transcript = self.remove_wake_word(transcript)
                except VoiceError as exc:
                    conversation = False
                    self.on_status(f"Fala não reconhecida: {exc}. Aguardando Jarvis novamente…")
                    continue
                finally:
                    recording.unlink(missing_ok=True)
                if not self._resume.is_set():
                    continue
                if transcript:
                    stop_text = self.WAKE_PATTERN.sub("", transcript, count=1)
                    if stop_text.casefold().strip(" .,!?:;") in self.STOP_PHRASES:
                        conversation = False
                        self.on_status("Conversa pausada. Diga Jarvis para iniciar outra.")
                        continue
                    self._resume.clear()
                    accepted = self.on_command(transcript)
                    if accepted is False:
                        self.on_status("Pedido de voz não enviado: aguarde a tarefa atual e diga Jarvis novamente.")
                        while not self._stop.is_set() and not self._resume.wait(0.2):
                            pass
                        conversation = False
                        continue
                    self.on_status("Comando enviado; conversação por voz ativa por até 20 s após a resposta.")
                    while not self._stop.is_set() and not self._resume.wait(0.2):
                        pass
                    conversation = True
                else:
                    conversation = bool(woke)
                    self.on_status("Jarvis ativada. Pode falar seu pedido." if woke else
                                   "Não reconheci a fala. Aguardando Jarvis…")
            self.on_status("Escuta contínua parada.")
        except Exception as exc:
            self.on_status(f"Escuta contínua indisponível: {exc}")

    def _listen_for_command(self, sd, np, *, idle_timeout=None):
        frames = queue.Queue(maxsize=64)
        recent = deque(maxlen=12)  # preserva a frase de ativação no início da transcrição

        def receive(indata, _frame_count, _time_info, status):
            if status:
                self.on_status(f"Áudio: {status}")
            chunk = indata[:, 0].copy()
            try:
                frames.put_nowait(chunk)
            except queue.Full:
                try:
                    frames.get_nowait()
                    frames.put_nowait(chunk)
                except (queue.Empty, queue.Full):
                    pass

        captured = []
        with self._capture_guard:
            if not self._resume.is_set():
                return None
            self._capture_idle.clear()
        try:
            with sd.InputStream(samplerate=self.voice.sample_rate, blocksize=self.FRAME_SAMPLES,
                                channels=1, dtype="int16", device=self.device,
                                callback=receive):
                idle_started = time.monotonic()
                last_frame = idle_started
                voiced = False
                quiet_frames = 0
                silence_limit = max(1, round(self.silence_seconds * self.voice.sample_rate / self.FRAME_SAMPLES))
                max_frames = max(1, round(self.max_command_seconds * self.voice.sample_rate / self.FRAME_SAMPLES))
                speech_threshold = max(self.voice.silence_rms, 180)
                while not self._stop.is_set():
                    if not self._resume.is_set():
                        return None
                    try:
                        chunk = frames.get(timeout=0.2)
                    except queue.Empty:
                        if time.monotonic() - last_frame >= 3:
                            raise VoiceError("Dispositivo sem entregar áudio por 3 segundos; "
                                             "confira a conexão e a entrada selecionada")
                        if idle_timeout is not None and time.monotonic() - idle_started >= idle_timeout:
                            return None
                        continue
                    last_frame = time.monotonic()
                    recent.append(chunk)
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                    if not voiced and rms >= speech_threshold:
                        voiced = True
                        captured.extend(recent)
                    elif voiced:
                        captured.append(chunk)
                        if rms >= speech_threshold:
                            quiet_frames = 0
                        else:
                            quiet_frames += 1
                            if quiet_frames >= silence_limit:
                                break
                    if len(captured) >= max_frames:
                        break
                    if idle_timeout is not None and time.monotonic() - idle_started >= idle_timeout:
                        return None
        except Exception as exc:
            raise VoiceError(f"Não foi possível escutar o microfone: {exc}") from exc
        finally:
            self._capture_idle.set()
        if self._stop.is_set():
            return None
        return np.concatenate(captured) if captured else None

    def _write_recording(self, samples):
        fd, location = tempfile.mkstemp(prefix="jarvis_command_", suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as raw:
                with wave.open(raw, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(self.voice.sample_rate)
                    wav.writeframes(samples.tobytes())
            return Path(location)
        except BaseException:
            Path(location).unlink(missing_ok=True)
            raise
