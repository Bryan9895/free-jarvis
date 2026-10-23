"""Teste local de captura e reconhecimento; não envia áudio/pedidos ao FCC."""
from array import array
from math import log10, sqrt
from pathlib import Path
import os
import re
import shutil
import subprocess
import time
import unicodedata
import wave

from .voice import VoiceIO, VoiceError

TEST_PHRASE = 'Jarvis, abra o Firefox e organize as minhas janelas.'


def signal_metrics(pcm):
    samples = array('h')
    samples.frombytes(pcm)
    if not samples:
        return {'rms': 0.0, 'peak': 0.0, 'dbfs': -96.0, 'clipping_percent': 0.0}
    rms = sqrt(sum(value * value for value in samples) / len(samples))
    peak = max(abs(value) for value in samples)
    return {'rms': round(rms / 32768, 6), 'peak': round(peak / 32768, 6),
            'dbfs': round(max(-96.0, 20 * log10(rms / 32768)), 1) if rms else -96.0,
            'clipping_percent': round(100 * sum(abs(value) >= 32760 for value in samples) / len(samples), 2)}


def compare_transcript(expected, recognized):
    def words(text):
        folded = ''.join(character for character in unicodedata.normalize('NFKD', text.casefold())
                         if not unicodedata.combining(character))
        return re.findall(r'\w+', folded)
    reference, hypothesis = words(expected), words(recognized)
    if not reference:
        return None
    previous = list(range(len(hypothesis) + 1))
    for i, word in enumerate(reference, 1):
        current = [i]
        for j, other in enumerate(hypothesis, 1):
            current.append(min(current[-1]+1, previous[j]+1, previous[j-1]+(word != other)))
        previous = current
    errors = previous[-1]
    return {'word_edits': errors, 'reference_words': len(reference),
            'word_error_rate': round(errors / len(reference), 3),
            'similarity_percent': round(100 * (1 - errors / max(len(reference), len(hypothesis))), 1)}


class VoiceDiagnostics:
    def __init__(self):
        self.recording = None
        self.voice = None
        self.model = None

    def probe(self, device=None):
        try:
            import sounddevice as sd
            configured = device if device is not None else os.getenv('JARVIS_AUDIO_DEVICE')
            info = sd.query_devices(configured, kind='input')
            sd.check_input_settings(device=configured, channels=1, dtype='int16', samplerate=16000)
        except ImportError as exc:
            raise VoiceError("Instale: pip install -e '.[voice]'") from exc
        except Exception as exc:
            raise VoiceError(f'Entrada indisponível ou sem suporte a 16 kHz: {exc}') from exc
        source = os.getenv('PULSE_SOURCE', '')
        name = str(info['name'])
        warnings = []
        if any(part in (name + ' ' + source).casefold() for part in ('.monitor', 'loopback', 'snd_aloop')):
            warnings.append('Entrada virtual/monitor selecionada: pode não ser seu microfone.')
        if name.casefold() in ('default', 'pulse', 'pipewire'):
            warnings.append('Entrada genérica: confira no Ubuntu se a fonte ativa é o microfone Bluetooth.')
        return {'status': 'available', 'device': name,
                'pulse_source': source or 'Padrão do sistema', 'sample_rate': 16000,
                'warnings': warnings}

    def capture(self, device=None, *, on_level=None):
        self.close()
        info = self.probe(device)
        voice = VoiceIO(device=device)
        self.recording = voice.record(6, allow_silence=True, on_level=on_level)
        with wave.open(str(self.recording), 'rb') as audio:
            metrics = signal_metrics(audio.readframes(audio.getnframes()))
        level = ('baixo_ou_silencio' if metrics['rms'] * 32768 < voice.silence_rms else
                 'possivel_saturacao' if metrics['clipping_percent'] >= 1 else 'sinal_detectado')
        return {**info, 'seconds': 6, 'signal': level, 'metrics': metrics}

    def replay(self):
        if self.recording is None or not self.recording.is_file():
            raise VoiceError('Grave uma amostra antes de reproduzir.')
        player = shutil.which('paplay') or shutil.which('aplay')
        if not player:
            raise VoiceError('Instale pulseaudio-utils ou alsa-utils para ouvir o teste.')
        try:
            result = subprocess.run([player, str(self.recording)], capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VoiceError('Falha ou tempo limite na reprodução da amostra.') from exc
        if result.returncode:
            raise VoiceError('Não foi possível reproduzir na saída padrão do Ubuntu.')
        return {'status': 'reproduzido', 'note': 'Confirme se você ouviu sua voz com clareza.'}

    def transcribe(self, model, expected):
        if self.recording is None or not self.recording.is_file():
            raise VoiceError('Grave uma amostra antes de testar o reconhecimento.')
        if model not in ('tiny', 'base', 'small'):
            raise VoiceError('Escolha tiny, base ou small.')
        if not isinstance(expected, str) or len(expected) > 500:
            raise VoiceError('Frase de referência inválida (até 500 caracteres).')
        if model != self.model:
            self.voice = None  # libera o modelo anterior antes de carregar outro
            self.voice = VoiceIO(model=model, language='pt')
            self.model = model
        started = time.monotonic()
        recognized = self.voice.transcribe(self.recording)
        return {'model': model, 'expected': expected, 'recognized': recognized,
                'seconds': round(time.monotonic()-started, 2),
                'comparison': compare_transcript(expected, recognized)}

    def close(self):
        if self.recording is not None:
            Path(self.recording).unlink(missing_ok=True)
            self.recording = None
        self.voice = None
        self.model = None
