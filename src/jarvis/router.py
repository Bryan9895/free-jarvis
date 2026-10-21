"""Roteamento leve de pedidos e seleção de ferramentas.

Não usa outra chamada ao LLM: o roteamento economiza prefill no modelo local.
Casos ambíguos são mantidos no agente normal com ferramentas.
"""
from __future__ import annotations

import re

# Apenas perguntas puramente informativas, com padrões restritos.
_INFO = (
    r"^(o que (?:é|significa)|quem (?:foi|é)|quanto é|qual (?:a diferença|o significado)|"
    r"explique (?:o conceito de|a diferença entre)|defina|resuma o conceito de)\b"
)
_ACTION = re.compile(
    r"\b(?:abra|abrir|clique|clicar|digite|digitar|mova|mover|apague|exclua|"
    r"salve|salvar|escreva|edite|pesquise|pesquisar|busque|procure|leia|"
    r"arquivo|pasta|navegador|janela|tela|desktop|mouse|teclado|"
    r"minha|meu|meus|minhas|agora|hoje|atual|recentes|online|"
    r"acesse|execute|terminal|crie|criar|liste|listar|encontre|verifique)\b",
    re.IGNORECASE,
)


def route(message: str, mode="auto") -> str:
    """Retorna 'fast' ou 'tools'. Modo fast é uma escolha explícita do usuário."""
    if mode not in ("auto", "fast", "tools"):
        raise ValueError("Modo desconhecido")
    if mode != "auto":
        return mode
    normalized = message.strip().lower()
    if len(normalized) > 180 or _ACTION.search(normalized):
        return "tools"
    if re.match(_INFO, normalized):
        return "fast"
    # Perguntas curtas sem verbos de ação e sem referências ao computador.
    if normalized.endswith("?") and len(normalized) <= 140:
        return "fast"
    if normalized in ("oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"):
        return "fast"
    return "tools"


def tool_catalog(message: str, available: list[dict]) -> list[dict]:
    """Por enquanto, o agente de ações recebe todo o catálogo autorizado.

    Evita regras de palavras-chave impedindo ferramentas necessárias.
    O caminho fast é o responsável por eliminar ferramentas com segurança.
    """
    return available
