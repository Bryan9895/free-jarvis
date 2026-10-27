"""Preferências locais sem segredos, com substituição atômica e esquema fechado."""
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class Preferences:
    version: int = 1
    stt_model: str = 'small'
    conversation_model: str = ''
    audio_device: str = ''
    piper_model: str = ''
    output_device: str = ''  # nome de sink Pulse/PipeWire, nunca índice SoundDevice
    silence_ms: int = 1000
    vad_threshold: float = 0.5
    voice_mode: str = 'continuous'
    followup_seconds: int = 20
    start_timeout_seconds: int = 20
    reconnect_attempts: int = 2
    wake_manifest: str = ''

    def validate(self):
        if self.version != 1:
            raise ValueError('Versão de preferências não suportada')
        for key in ('stt_model', 'conversation_model', 'audio_device', 'piper_model', 'output_device', 'wake_manifest'):
            value = getattr(self, key)
            if not isinstance(value, str) or len(value) > 4096 or '\x00' in value:
                raise ValueError('Preferência inválida: ' + key)
        if self.stt_model not in ('tiny', 'base', 'small'):
            raise ValueError('Modelo STT inválido')
        if type(self.silence_ms) is not int or not 600 <= self.silence_ms <= 1800:
            raise ValueError('Silêncio deve estar entre 600 e 1800 ms')
        if type(self.vad_threshold) not in (int, float) or not math.isfinite(self.vad_threshold) or not 0.1 <= self.vad_threshold <= 0.9:
            raise ValueError('Limiar VAD deve estar entre 0.1 e 0.9')
        if self.voice_mode not in ('continuous', 'manual', 'muted'):
            raise ValueError('Modo de voz inválido')
        for key, label, minimum, maximum in (('followup_seconds', 'Seguimento', 5, 120),
                ('start_timeout_seconds', 'Espera para começar', 3, 120),
                ('reconnect_attempts', 'Tentativas de reconexão', 0, 5)):
            value = getattr(self, key)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f'{label} deve estar entre {minimum} e {maximum}')
        return self

    def effective(self):
        values = asdict(self)
        for key, variable in {'stt_model': 'JARVIS_WHISPER_MODEL',
                              'conversation_model': 'FCC_MODEL', 'audio_device': 'JARVIS_AUDIO_DEVICE',
                              'piper_model': 'JARVIS_PIPER_MODEL', 'output_device': 'JARVIS_AUDIO_OUTPUT',
                              'wake_manifest': 'JARVIS_WAKE_MANIFEST',
                              'voice_mode': 'JARVIS_VOICE_MODE'}.items():
            if variable in os.environ:
                values[key] = os.environ[variable]
        if 'JARVIS_SILENCE_MS' in os.environ:
            values['silence_ms'] = int(os.environ['JARVIS_SILENCE_MS'])
        if 'JARVIS_VAD_THRESHOLD' in os.environ:
            values['vad_threshold'] = float(os.environ['JARVIS_VAD_THRESHOLD'])
        for key, variable in (('followup_seconds', 'JARVIS_FOLLOWUP_SECONDS'),
                              ('start_timeout_seconds', 'JARVIS_START_TIMEOUT_SECONDS'),
                              ('reconnect_attempts', 'JARVIS_AUDIO_RETRIES')):
            if variable in os.environ:
                values[key] = int(os.environ[variable])
        return Preferences(**values).validate()


class PreferenceStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('JARVIS_PREFERENCES',
            '~/.config/jarvis-fcc/preferences.json')).expanduser()
        self.error = None

    def load(self):
        self.error = None
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict) or set(data) - set(asdict(Preferences())):
                raise ValueError('Esquema de preferências inválido')
            return Preferences(**data).validate()
        except FileNotFoundError:
            return Preferences()
        except (OSError, ValueError, TypeError) as exc:
            self.error = str(exc)
            return Preferences()

    def save(self, preferences):
        preferences.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.preferences-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(asdict(preferences), stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
