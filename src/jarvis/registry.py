"""Catálogo de ferramentas e concessões de capacidade por sessão.

O registro não carrega código de terceiros automaticamente. Uma extensão precisa
ser registrada explicitamente com esquema, capacidade e função executora.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ToolEntry:
    spec: dict
    capability: str
    handler: str | Callable


class ToolRegistry:
    def __init__(self):
        self._entries: dict[str, ToolEntry] = {}

    def register(self, spec: dict, capability: str, handler: str | Callable):
        name = spec.get("name") if isinstance(spec, dict) else None
        if (not isinstance(name, str) or not name.isidentifier()
                or spec.get("type") != "function"
                or not isinstance(spec.get("parameters"), dict)):
            raise ValueError("Esquema de ferramenta inválido")
        if name in self._entries:
            raise ValueError(f"Ferramenta duplicada: {name}")
        if not isinstance(capability, str) or not capability:
            raise ValueError("Capacidade inválida")
        if not (isinstance(handler, str) and handler.isidentifier() or callable(handler)):
            raise ValueError("Executor de ferramenta inválido")
        self._entries[name] = ToolEntry(spec, capability, handler)

    def get(self, name: str) -> ToolEntry | None:
        if not isinstance(name, str):
            return None
        return self._entries.get(name)

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(entry.capability for entry in self._entries.values())

    def available_specs(self, enabled: set[str] | frozenset[str], *, desktop_input=False) -> list[dict]:
        return [entry.spec for name, entry in self._entries.items()
                if entry.capability in enabled and (name != "desktop_input" or desktop_input)]


class CapabilityPolicy:
    """Concessões locais; auto-approve não modifica esta lista."""

    def __init__(self, registry: ToolRegistry, enabled: set[str] | None = None):
        known = registry.capabilities
        selected = known if enabled is None else frozenset(enabled)
        unknown = selected - known
        if unknown:
            raise ValueError("Capacidades desconhecidas: " + ", ".join(sorted(unknown)))
        self.enabled = selected

    def permits(self, entry: ToolEntry) -> bool:
        return entry.capability in self.enabled
