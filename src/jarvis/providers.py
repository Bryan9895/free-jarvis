"""Contrato estrutural para provedores de modelos usados pelo núcleo."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ModelProvider(Protocol):
    """Operações de modelo necessárias à aplicação e às interfaces."""

    active_model: str

    def responses(self, payload: dict) -> dict:
        """Envia uma solicitação Responses e retorna a resposta concluída."""
        ...

    def available_models(self) -> list[str]:
        """Lista modelos anunciados compatíveis com o adaptador."""
        ...

    def select_model(self, name: str) -> str:
        """Seleciona um modelo conhecido pelo adaptador."""
        ...


class StreamingModelProvider(ModelProvider, Protocol):
    def stream_responses(self, payload: dict, *, on_event=None,
                         cancel_token=None, deadline=None) -> dict:
        """Texto público incremental e resultado terminal consolidado."""
        ...
