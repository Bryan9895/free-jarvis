"""Configuração sem dependências externas. Segredos exclusivamente por ambiente."""
from dataclasses import dataclass
import os
from pathlib import Path

@dataclass(frozen=True)
class Config:
    url: str
    model: str
    token: str
    workspace: Path
    db: Path
    profile: str = 'fcc'
    local_model: str = 'gemma4:e2b'
    ollama_host: str = 'http://127.0.0.1:11434'
    openjarvis_python: str = ''

    @classmethod
    def from_env(cls):
        from .preferences import PreferenceStore
        preferences = PreferenceStore().load().effective()
        from .local_setup import managed_python
        saved_model = preferences.conversation_model
        return cls(
            os.getenv("FCC_URL", "http://127.0.0.1:8082").rstrip("/"),
            (lambda value: "" if value.strip().upper() in {"ID_DO_MODELO", "MODEL_ID", "YOUR_MODEL_ID"} else value.strip())(os.getenv("FCC_MODEL", saved_model)),
            os.getenv("FCC_TOKEN", ""),
            Path(os.getenv("JARVIS_WORKSPACE", "~/Projetos")).expanduser().resolve(),
            Path(os.getenv("JARVIS_DB", "~/.local/share/jarvis-fcc/memory.sqlite3")).expanduser(),
            preferences.inference_profile,
            preferences.local_model,
            os.getenv('JARVIS_OLLAMA_HOST', 'http://127.0.0.1:11434'),
            os.getenv('JARVIS_OPENJARVIS_PYTHON') or managed_python(),
        )
