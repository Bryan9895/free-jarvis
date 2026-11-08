"""Síntese ElevenLabs em WAV PCM para o reprodutor desktop existente.

Não exige SDK, JS ou servidor HTTP local. Requer internet e ELEVENLABS_API_KEY.
Nunca inclui chaves nas mensagens, nos arquivos ou no histórico.
"""
from __future__ import annotations
import json
import os
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .cancellation import CancelledError

DEFAULT_VOICE = "pNInz6obpgDQGcFmaJgB"  # Voz Adam padrão do ElevenLabs.
DEFAULT_MODEL = "eleven_flash_v2_5"
MAX_AUDIO_BYTES = 12 * 1024 * 1024


def configured():
    return bool(os.getenv("ELEVENLABS_API_KEY", "").strip())


def synthesize(text, filename, cancel, *, voice_id=None, model_id=None, speed=1.0):
    """Recebe PCM S16LE 16 kHz e grava WAV somente após o fluxo terminar."""
    key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Configure ELEVENLABS_API_KEY para usar a voz ADAM.")
    voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE).strip()
    model_id = model_id or os.getenv("ELEVENLABS_MODEL_ID", DEFAULT_MODEL).strip()
    if not voice_id or not voice_id.isalnum():
        raise ValueError("ELEVENLABS_VOICE_ID inválido")
    if not 0.7 <= float(speed) <= 1.2:
        raise ValueError("Velocidade da voz fora do intervalo")
    if cancel.is_set():
        raise CancelledError("Síntese cancelada")

    request = Request(
        "https://api.elevenlabs.io/v1/text-to-speech/" + voice_id +
        "/stream?output_format=pcm_16000",
        data=json.dumps({
            "text": str(text), "model_id": model_id,
            "voice_settings": {"speed": float(speed)},
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/octet-stream",
            "xi-api-key": key,
        },
        method="POST",
    )
    filename = Path(filename)
    temporary = filename.with_name(filename.name + ".incomplete")
    total = 0
    try:
        with urlopen(request, timeout=30) as response, wave.open(str(temporary), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            while True:
                if cancel.is_set():
                    raise CancelledError("Síntese ElevenLabs cancelada")
                chunk = response.read(4096)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_AUDIO_BYTES:
                    raise RuntimeError("A resposta de áudio excedeu o limite de segurança.")
                if len(chunk) % 2:
                    raise RuntimeError("Fluxo PCM inválido")
                output.writeframesraw(chunk)
        if total < 2:
            raise RuntimeError("ElevenLabs não retornou áudio")
        if cancel.is_set():
            raise CancelledError("Síntese ElevenLabs cancelada")
        os.replace(temporary, filename)
    except HTTPError as exc:
        # Não imprimir resposta HTTP: pode incluir dados ou informações privadas.
        raise RuntimeError(f"ElevenLabs recusou a síntese (HTTP {exc.code}); verifique chave, voz e créditos.") from None
    except (URLError, TimeoutError, ConnectionError) as exc:
        raise RuntimeError("ElevenLabs indisponível; confirme internet e conexão.") from exc
    finally:
        temporary.unlink(missing_ok=True)
