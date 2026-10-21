"""Camada de voz local e opcional: SoundDevice -> faster-whisper -> Piper."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

class VoiceError(RuntimeError):
    """Falha recuperável de áudio."""

class VoiceIO:
    def __init__(self, model="tiny", language="pt", piper_model="", sample_rate=16000):
        self.model_name = model
        self.language = language
        self.piper_model = Path(piper_model).expanduser() if piper_model else None
        self.sample_rate = sample_rate
        self._stt = None

    def record(self, seconds=6):
        """Grava WAV PCM16 temporário; o chamador deve apagar o arquivo."""
        if not 1 <= seconds <= 15:
            raise VoiceError("A gravação deve durar entre 1 e 15 segundos")
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise VoiceError("Instale: pip install -e '.[voice]'") from exc
        try:
            audio = sd.rec(int(self.sample_rate * seconds), samplerate=self.sample_rate,
                           channels=1, dtype="int16")
            sd.wait()
        except Exception as exc:
            raise VoiceError(f"Microfone indisponível: {exc}") from exc
        fd, location = tempfile.mkstemp(prefix="jarvis_mic_", suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as raw:
                with wave.open(raw, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(self.sample_rate)
                    wav.writeframes(audio.tobytes())
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
                                                vad_filter=True, beam_size=1)
            return " ".join(segment.text.strip() for segment in segments).strip()
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
