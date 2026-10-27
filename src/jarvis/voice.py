"""Camada de voz local e opcional: SoundDevice -> faster-whisper -> Piper."""
from __future__ import annotations
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from contextlib import nullcontext
from functools import wraps
from array import array
from math import sqrt
from .latency import TurnTrace

class VoiceError(RuntimeError):
    """Falha recuperável de áudio."""


class PendingVoiceTurn(VoiceError):
    """Áudio mantido sem intenção executável até continuação explícita."""


from .capture import coordinator
_capture_owner = coordinator.lock


def exclusive_capture(method):
    """Exclusão também entre adaptadores de diagnóstico e conversa."""
    @wraps(method)
    def capture(*args, **kwargs):
        if not _capture_owner.acquire(blocking=False):
            raise VoiceError("Microfone ocupado por outra captura; pare-a antes de continuar")
        try:
            return method(*args, **kwargs)
        finally:
            _capture_owner.release()
    return capture

class VoiceIO:
    def __init__(self, model=None, language="pt", piper_model="", sample_rate=16000,
                 device=None, silence_rms=150, output_device=None, session_id=None):
        from .preferences import PreferenceStore
        preferences = PreferenceStore().load().effective()
        self.model_name = os.getenv('JARVIS_WHISPER_MODEL', model or preferences.stt_model)
        self.language = language
        piper_model = os.getenv('JARVIS_PIPER_MODEL', piper_model or preferences.piper_model)
        self.piper_model = Path(piper_model).expanduser() if piper_model else None
        self.sample_rate = sample_rate
        self.device = os.getenv('JARVIS_AUDIO_DEVICE', device if device is not None else preferences.audio_device or None)
        if isinstance(self.device, str):
            self.device = self.device.split(': ', 1)[-1]
        self.silence_rms = silence_rms
        self.output_device = os.getenv('JARVIS_AUDIO_OUTPUT', output_device if output_device is not None else preferences.output_device)
        self.silence_seconds = preferences.silence_ms / 1000
        self.vad_threshold = preferences.vad_threshold
        self.followup_seconds = preferences.followup_seconds
        self.start_timeout_seconds = preferences.start_timeout_seconds
        self.reconnect_attempts = preferences.reconnect_attempts
        self.wake_manifest = preferences.wake_manifest
        from uuid import uuid4
        self.session_id = session_id or uuid4().hex
        self._stt = None
        self._speech_cancel = threading.Event()
        self.pending_audio = None
        self._continue_pending = False

    def discard_pending(self):
        recording, self.pending_audio = self.pending_audio, None
        if recording is not None:
            recording.close()

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

    @staticmethod
    def output_devices():
        try:
            result = subprocess.run(['pactl', 'list', 'short', 'sinks'], capture_output=True,
                                    text=True, timeout=5, check=False)
            if result.returncode:
                raise VoiceError('Não foi possível listar as saídas Pulse/PipeWire')
            return [line.split()[1] for line in result.stdout.splitlines() if len(line.split()) >= 2]
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VoiceError('Listagem requer pactl e servidor Pulse/PipeWire disponível') from exc

    @exclusive_capture
    def record(self, seconds=6, *, allow_silence=False, on_level=None):
        """Grava WAV PCM16 temporário; o chamador deve apagar o arquivo."""
        if not 1 <= seconds <= 15:
            raise VoiceError("A gravação deve durar entre 1 e 15 segundos")
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise VoiceError("Instale: pip install -e '.[voice]'") from exc
        try:
            from .audio_devices import input_format
            selected = input_format(sd, self.device, self.sample_rate)
            chunks = []
            completed = threading.Event()
            lost = threading.Event()
            remaining = int(selected.rate * seconds)

            def receive(indata, _count, _timing, _status):
                nonlocal remaining
                if _status:
                    lost.set()
                take = min(remaining, len(indata))
                if take:
                    chunk = indata[:take].tobytes()
                    chunks.append(chunk)
                    remaining -= take
                if remaining == 0:
                    completed.set()
                    raise sd.CallbackStop

            stream = sd.InputStream(samplerate=selected.rate, channels=selected.channels,
                                    dtype="int16", device=self.device, callback=receive,
                                    blocksize=max(1, selected.rate // 10))
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
            if lost.is_set():
                raise VoiceError('Perda de quadros na gravação; amostra descartada')
            if selected.channels == 2:
                import numpy as np
                samples = np.frombuffer(audio_bytes, dtype=np.int16).reshape(-1, 2)
                audio_bytes = np.mean(samples, axis=1).astype(np.int16).tobytes()
            if on_level is not None:
                from .voice_diagnostics import signal_metrics
                on_level({**signal_metrics(audio_bytes), 'elapsed': seconds})
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
                    wav.setframerate(selected.rate)
                    wav.writeframes(audio_bytes)
            return Path(location)
        except BaseException:
            Path(location).unlink(missing_ok=True)
            raise

    def transcribe(self, filename, *, beam_size=5, vad_filter=True):
        if type(beam_size) is not int or beam_size not in (1, 3, 5) or type(vad_filter) is not bool:
            raise VoiceError('Perfil STT inválido')
        filename = Path(filename)
        if not filename.is_file():
            raise VoiceError("Arquivo de gravação inexistente")
        try:
            from .stt_cache import whisper_model
            trace = getattr(self, 'last_capture_trace', None)
            if trace is not None:
                trace.mark('stt_queued')
                trace.mark('stt_cache_start')
                coordinator.transition(trace, 'transcrevendo', 'transcrição local iniciada',
                                       getattr(self, '_capture_emit', lambda _: None))
            with nullcontext(self._stt) if self._stt is not None else whisper_model(self.model_name) as model:
                if trace is not None:
                    trace.mark('stt_model_ready')
                    trace.mark('stt_start')
                segments, _ = model.transcribe(str(filename), language=self.language,
                                                vad_filter=vad_filter, beam_size=beam_size,
                                                condition_on_previous_text=False)
                segments = list(segments)
                if any(getattr(segment, 'no_speech_prob', 0) >= 0.6 and
                       getattr(segment, 'avg_logprob', 0) < -1.0 for segment in segments):
                    raise VoiceError('Transcrição incerta; repita o pedido brevemente')
                text = " ".join(segment.text.strip() for segment in segments).strip()
                if trace is not None:
                    trace.mark('stt_end')
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
        from .speech_text import spoken_text, speech_chunks
        text = spoken_text(text)
        if not text.strip():
            return 'empty'
        return self.speak_stream(speech_chunks(text))

    def speak_stream(self, chunks):
        if self.piper_model is None:
            return 'disabled'
        if not self.piper_model.is_file():
            raise VoiceError('Modelo de voz Piper não encontrado em JARVIS_PIPER_MODEL')
        if self.output_device and not shutil.which('paplay'):
            raise VoiceError('Saída selecionada requer paplay (pulseaudio-utils)')
        if not self.output_device and not shutil.which('aplay'):
            raise VoiceError("Instale 'alsa-utils' para executar aplay")
        from .audio_output import play_pipeline
        with coordinator.output(self._speech_cancel):
            return play_pipeline(self, chunks)

    def warmup(self):
        """Prepara Piper residente por ação explícita, sem download ou player."""
        if self.piper_model is None or not self.piper_model.is_file():
            raise VoiceError('Selecione uma voz local instalada antes de preparar')
        from .tts_engine import synthesizer
        fd, filename = tempfile.mkstemp(prefix='jarvis_warmup_', suffix='.wav')
        os.close(fd)
        try:
            synthesizer.synthesize(self.piper_model, 'Voz preparada.', Path(filename), self._speech_cancel)
        finally:
            Path(filename).unlink(missing_ok=True)

    def prepare_speech(self):
        self._speech_cancel.clear()

    def cancel_speech(self):
        self._speech_cancel.set()

    def _run_audio(self, command, *, text=None):
        from .cancellation import CancelledError
        if self._speech_cancel.is_set():
            raise CancelledError("Resposta falada cancelada")
        process = subprocess.Popen(command, stdin=subprocess.PIPE if text is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 90
        try:
            pending = text
            while True:
                if self._speech_cancel.is_set():
                    raise CancelledError("Resposta falada cancelada")
                if time.monotonic() >= deadline:
                    raise VoiceError("Tempo limite de síntese/reprodução excedido")
                try:
                    _, error = process.communicate(input=pending, timeout=0.1)
                    if process.returncode:
                        raise VoiceError("Falha de síntese/saída local: " + error[-500:])
                    return
                except subprocess.TimeoutExpired:
                    pending = None
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()

    def listen_once(self, seconds=6):
        recording = self.record(seconds)
        try:
            return self.transcribe(recording)
        finally:
            recording.unlink(missing_ok=True)

    def record_turn(self, *, cancel=None, finish=None, on_level=None, continue_pending=False):
        """Botão usa o mesmo endpoint do contínuo, sem janela fixa de pedido."""
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise VoiceError("Instale: pip install -e '.[voice]'") from exc
        listener = WakeWordConversation(self, lambda _: None, silence_seconds=self.silence_seconds)
        self._continue_pending = continue_pending
        if cancel is not None:
            listener._stop = cancel
        samples = listener._listen_for_command(sd, np, idle_timeout=self.start_timeout_seconds,
                                              finish=finish, on_level=on_level)
        if samples is None:
            raise VoiceError("Captura cancelada ou nenhuma fala recebida; pedido não enviado")
        return listener._write_recording(samples)


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
                 *, device=None, silence_seconds=None,
                 max_command_seconds=120, on_transcript=lambda _text: None,
                 activity_factory=None, wake_engine=None, on_event=lambda _: None):
        self.voice = voice
        self.on_command = on_command
        self.on_status = on_status
        self.on_transcript = on_transcript
        self.activity_factory = activity_factory
        self.device = voice.device if device is None else device
        self.silence_seconds = voice.silence_seconds if silence_seconds is None else silence_seconds
        self.max_command_seconds = max_command_seconds
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._thread = None
        self._capture_guard = threading.Lock()
        self._capture_idle = threading.Event()
        self._capture_idle.set()
        self._generation = 0
        self.capture_rate = voice.sample_rate
        self.on_event = on_event
        self.wake_engine = wake_engine
        self._acoustically_activated = False
        self.audio_metrics = {'frames': 0, 'lost_turns': 0, 'queue_peak': 0}

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
        self._generation += 1
        self._stop.set()
        self._resume.set()
        self.voice.discard_pending()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=timeout)
        return self._thread is None or not self._thread.is_alive()

    def pause(self, timeout=0):
        with self._capture_guard:
            self._generation += 1
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

            if self.wake_engine is None and self.voice.wake_manifest:
                try:
                    from .wake_word import WakeArtifact, OnnxWakeWordEngine
                    self.wake_engine = OnnxWakeWordEngine(WakeArtifact.load(self.voice.wake_manifest))
                except Exception as exc:
                    self.on_status('Detector acústico indisponível: ' + str(exc))
            self.on_status('Aguardando Jarvis — detector acústico local.' if self.wake_engine is not None else
                           'Aguardando Jarvis — fallback por transcrição local; detector acústico não validado.')
            conversation = False
            capture_failures = 0
            while not self._stop.is_set():
                if not self._resume.wait(0.2):
                    continue
                woke = not conversation
                self._waiting_activation = woke
                self._following_up = conversation
                self._require_wake = woke and self.wake_engine is not None
                self._acoustically_activated = False
                if self.wake_engine is not None:
                    self.wake_engine.reset()
                generation = self._generation
                try:
                    samples = self._listen_for_command(
                        sd, np, idle_timeout=self.voice.followup_seconds if conversation else None)
                except PendingVoiceTurn as exc:
                    conversation = False
                    self._resume.clear()
                    self.on_status(str(exc))
                    continue
                except VoiceError as exc:
                    conversation = False
                    self.on_status(f"Turno descartado: {exc}")
                    capture_failures += 1
                    if capture_failures > self.voice.reconnect_attempts:
                        raise
                    self.on_status(f"Recuperando áudio: tentativa {capture_failures}/{self.voice.reconnect_attempts}…")
                    if self._stop.wait(0.5 * 2 ** (capture_failures - 1)):
                        break
                    continue
                capture_failures = 0
                if self._stop.is_set():
                    break
                if not self._resume.is_set() or self._stop.is_set() or generation != self._generation:
                    continue
                if samples is None:
                    conversation = False
                    self.on_status("Conversa pausada. Diga Jarvis para iniciar outra.")
                    continue
                self.on_status("Entendendo: transcrevendo localmente e verificando ativação no fallback…")
                recording = self._write_recording(samples)
                try:
                    transcript = self.voice.transcribe(recording)
                    self.on_transcript(transcript)
                    if woke and not self._acoustically_activated:
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
                if not self._resume.is_set() or self._stop.is_set() or generation != self._generation:
                    continue
                if transcript:
                    stop_text = self.WAKE_PATTERN.sub("", transcript, count=1)
                    if stop_text.casefold().strip(" .,!?:;") in self.STOP_PHRASES:
                        conversation = False
                        self.on_status("Conversa pausada. Diga Jarvis para iniciar outra.")
                        continue
                    self._resume.clear()
                    from .latency import TracedText
                    accepted = self.on_command(TracedText(transcript,
                        getattr(self.voice, 'last_capture_trace', None)))
                    if accepted is False:
                        self.on_status("Pedido de voz não enviado: aguarde a tarefa atual e diga Jarvis novamente.")
                        while not self._stop.is_set() and not self._resume.wait(0.2):
                            pass
                        conversation = False
                        continue
                    self.on_status(f"Comando enviado; conversação por voz ativa por até {self.voice.followup_seconds} s após a resposta.")
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

    @exclusive_capture
    def _listen_for_command(self, sd, np, *, idle_timeout=None, finish=None, on_level=None):
        from .audio_endpoint import AudioEndpoint, TurnLimitError
        from .latency import TurnTrace
        from .recording import PCMRecording
        pending = self.voice.pending_audio
        if pending is not None and not self.voice._continue_pending:
            raise PendingVoiceTurn('Pedido pendente. Use Continuar pendente ou descarte; nenhuma ação foi executada.')
        self.voice._continue_pending = False
        self.voice.pending_audio = None
        trace = self.voice.last_capture_trace = pending.trace if pending is not None else TurnTrace(session_id=self.voice.session_id)
        recording = pending if pending is not None else PCMRecording(16000, trace)
        retained = False
        successful = False
        capture_generation = self._generation
        self.voice._capture_emit = self.on_event
        trace.mark('capture_start')
        state = ('aguardando_ativacao' if getattr(self, '_waiting_activation', getattr(self, '_require_wake', False))
                 else 'aguardando_seguimento' if getattr(self, '_following_up', False) else 'aguardando_fala')
        coordinator.transition(trace, state, 'captura exclusiva iniciada', self.on_event)
        last_speech_at = None
        frames = queue.Queue(maxsize=64)
        lost = threading.Event()

        def receive(indata, _frame_count, _time_info, status):
            if status:
                lost.set()
            chunk = indata.copy()
            try:
                frames.put_nowait((time.monotonic(), chunk))
            except queue.Full:
                lost.set()

        with self._capture_guard:
            if not self._resume.is_set():
                return None
            self._capture_idle.clear()
        stage = 'Entrada de áudio'
        try:
            from .audio_devices import input_format
            from .audio_activity import PCMNormalizer, SileroActivity
            selected = input_format(sd, self.device, self.voice.sample_rate)
            normalizer = PCMNormalizer(selected.rate, 16000)
            self.on_status('Carregando detector local de fala (VAD)…')
            stage = 'VAD local'
            activity = self.activity_factory() if self.activity_factory else SileroActivity(threshold=self.voice.vad_threshold)
            self.capture_rate = 16000
            self.on_status(f'Entrada SoundDevice: {selected.name}; {selected.rate} Hz, {selected.channels} canal(is). Fonte Pulse deve ser conferida separadamente.')
            endpoint = AudioEndpoint(16000, silence_seconds=self.silence_seconds,
                                     max_seconds=self.max_command_seconds,
                                     preroll_seconds=0 if pending is not None else .8,
                                     chunk_sink=recording.append)
            blocksize = round(self.FRAME_SAMPLES * selected.rate / 16000)
            stage = 'Captura de áudio'
            with sd.InputStream(samplerate=selected.rate, blocksize=blocksize,
                                channels=selected.channels, dtype="int16", device=self.device,
                                callback=receive):
                idle_started = time.monotonic()
                last_frame = idle_started
                wake_wait_started = None
                while not self._stop.is_set():
                    if not self._resume.is_set() or capture_generation != self._generation:
                        return None
                    if lost.is_set():
                        raise VoiceError("Perda de quadros/overflow; pedido descartado, repita a fala")
                    if finish is not None and finish.is_set() and frames.empty():
                        break
                    try:
                        captured_at, chunk = frames.get(timeout=0.2)
                    except queue.Empty:
                        if time.monotonic() - last_frame >= 3:
                            raise VoiceError("Dispositivo sem entregar áudio por 3 segundos; "
                                             "confira a conexão e a entrada selecionada")
                        if not endpoint.started and idle_timeout is not None and time.monotonic() - idle_started >= idle_timeout:
                            return None
                        continue
                    last_frame = time.monotonic()
                    self.audio_metrics['frames'] += 1
                    self.audio_metrics['last_frame_at'] = captured_at
                    self.audio_metrics['queue_delay_ms'] = max(0, (last_frame - captured_at) * 1000)
                    self.audio_metrics['queue_peak'] = max(self.audio_metrics['queue_peak'], frames.qsize() + 1)
                    chunk = normalizer.feed(chunk)
                    if not len(chunk):
                        continue
                    self.audio_metrics['rms'] = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                    if on_level is not None:
                        from .voice_diagnostics import signal_metrics
                        on_level(signal_metrics(chunk.tobytes()))
                    was_started = endpoint.started
                    active = activity.active(chunk)
                    if getattr(self, '_require_wake', False):
                        if self.wake_engine.process(chunk):
                            self._require_wake = False
                            self._acoustically_activated = True
                            wake_wait_started = last_frame
                            trace.mark('wake_detected')
                            self.on_status('Jarvis ativado. Ouvindo o pedido.')
                            coordinator.transition(trace, 'ouvindo', 'ativação acústica', self.on_event)
                        else:
                            # Pré-áudio permanece no endpoint, mas não inicia
                            # um turno/STT para toda fala ambiente.
                            endpoint.feed(chunk, False)
                            continue
                    if (wake_wait_started is not None and not endpoint.started and
                            last_frame - wake_wait_started >= self.voice.start_timeout_seconds):
                        return None
                    if active:
                        last_speech_at = captured_at
                    ended = endpoint.feed(chunk, active)
                    if len(recording) >= 16000 * 600:
                        raise VoiceError('Teto total de 10 minutos atingido; áudio descartado sem execução. Divida o pedido.')
                    if endpoint.started and not was_started:
                        self.on_status('Ouvindo')
                        coordinator.transition(trace, 'ouvindo', 'fala detectada', self.on_event)
                    if ended:
                        if last_speech_at is not None:
                            trace.mark('last_speech_audio', at=last_speech_at)
                        trace.mark('endpoint_decided')
                        break
                    if not endpoint.started and idle_timeout is not None and time.monotonic() - idle_started >= idle_timeout:
                        return None
                if lost.is_set():
                    raise VoiceError("Perda de quadros/overflow; pedido descartado, repita a fala")
                tail = normalizer.flush()
                if len(tail) and endpoint.started:
                    if endpoint.samples + len(tail) >= endpoint.limit:
                        raise VoiceError('Limite de segurança atingido; pedido não enviado')
                    endpoint.store_chunk(tail)
                successful = not self._stop.is_set() and capture_generation == self._generation
        except TurnLimitError as exc:
            if self._stop.is_set() or capture_generation != self._generation:
                return None
            if len(recording) >= 16000 * 600:
                raise VoiceError('Teto total de 10 minutos atingido; áudio descartado sem execução.') from exc
            self.voice.pending_audio = recording
            retained = True
            trace.mark('capture_pending')
            coordinator.transition(trace, 'pedido_pendente', 'teto do segmento; sem execução', self.on_event)
            raise PendingVoiceTurn('Pedido pendente: limite do segmento atingido. Continue pelo botão Continuar pendente ou descarte. Nenhuma ação foi executada.') from exc
        except PendingVoiceTurn:
            raise
        except Exception as exc:
            if lost.is_set():
                self.audio_metrics['lost_turns'] += 1
            raise VoiceError(f"{stage} indisponível: {exc}") from exc
        finally:
            trace.mark('capture_released')
            coordinator.transition(trace, 'captura_liberada', 'dispositivo liberado', self.on_event)
            self._capture_idle.set()
            if not retained and not successful:
                recording.close()
        if self._stop.is_set():
            return None
        if not len(recording):
            recording.close()
            return None
        recording.complete = True
        return recording

    def _write_recording(self, samples):
        fd, location = tempfile.mkstemp(prefix="jarvis_command_", suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as raw:
                with wave.open(raw, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    # STT decodifica/ressample uma vez a partir da taxa nativa.
                    wav.setframerate(self.capture_rate)
                    if hasattr(samples, 'write_to'):
                        samples.write_to(wav)
                    else:
                        wav.writeframes(samples.tobytes())
            return Path(location)
        except BaseException:
            Path(location).unlink(missing_ok=True)
            raise
        finally:
            if hasattr(samples, 'write_to'):
                samples.close()
