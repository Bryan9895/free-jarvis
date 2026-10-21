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

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("FCC_URL", "http://127.0.0.1:8082").rstrip("/"),
            (lambda value: "" if value.strip().upper() in {"ID_DO_MODELO", "MODEL_ID", "YOUR_MODEL_ID"} else value.strip())(os.getenv("FCC_MODEL", "")),
            os.getenv("FCC_TOKEN", ""),
            Path(os.getenv("JARVIS_WORKSPACE", "~/Projetos")).expanduser().resolve(),
            Path(os.getenv("JARVIS_DB", "~/.local/share/jarvis-fcc/memory.sqlite3")).expanduser(),
        )
