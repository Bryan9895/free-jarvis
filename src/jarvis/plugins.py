"""Carregamento explícito de plugins Python confiáveis.

Um plugin exporta register_tools(registry) e registra esquemas, capacidades e
executores. Importar o módulo executa código Python: use apenas módulos que o
operador instalou e listou deliberadamente em JARVIS_PLUGINS.
"""
from __future__ import annotations

import importlib
import re

from .registry import ToolRegistry

_MODULE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\Z")


def load_plugins(base: ToolRegistry, configured: str) -> ToolRegistry:
    registry = base.copy()
    names = [part.strip() for part in configured.split(",") if part.strip()]
    if len(names) != len(set(names)):
        raise ValueError("Plugin repetido em JARVIS_PLUGINS")
    for name in names:
        if not _MODULE.fullmatch(name):
            raise ValueError("Nome de plugin inválido: " + name)
        try:
            module = importlib.import_module(name)
        except Exception as exc:
            raise ValueError("Não foi possível importar plugin " + name + ": " + str(exc)) from exc
        register = getattr(module, "register_tools", None)
        if not callable(register):
            raise ValueError("Plugin sem register_tools(registry): " + name)
        try:
            register(registry)
        except Exception as exc:
            raise ValueError("Falha ao registrar plugin " + name + ": " + str(exc)) from exc
    return registry
