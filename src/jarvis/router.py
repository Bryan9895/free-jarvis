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
    r"acesse|execute|terminal|crie|criar|liste|listar|encontre|verifique|"
    r"monitores?|workspaces?|(?:área|area)s? de trabalho)\b",
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
    """Seleciona um conjunto mínimo só em intenções inequívocas.

    Inspirado na resolução de ferramentas por capacidade do OpenJarvis,
    porém sem importar sua infraestrutura. Não concede permissões novas:
    apenas reduz ferramentas previamente autorizadas.
    Casos compostos/ambíguos preservam o catálogo original.
    """
    import unicodedata

    def fold(value):
        normalized = unicodedata.normalize("NFKD", value.casefold())
        return "".join(c for c in normalized if not unicodedata.combining(c))

    normalized = fold(message).strip()
    normalized = re.sub(r"^jarvis[,.:!\s]+", "", normalized)
    if len(normalized) > 180 or "\n" in normalized:
        return available
    if re.search(r"\b(?:ambiente|ambientes)\b", normalized):
        if re.search(r"\b(?:salve|salvar|guarde|guardar)\b", normalized):
            return [t for t in available if t.get("name") == "save_desktop_profile"]
        if re.search(r"\b(?:liste|listar|mostre|mostrar|quais)\b", normalized):
            return [t for t in available if t.get("name") == "list_desktop_profiles"]
        if re.search(r"\b(?:abra|abrir|prepare|preparar|restaure|restaurar|"
                      r"recupere|recuperar|carregue|carregar)\b", normalized):
            return [t for t in available if t.get("name") == "restore_desktop_profile"]
    monitor_destination = re.search(
        r"\b(?:(?:outro|segundo|terceiro|externo|\d+) monitor|"
        r"monitor (?:\d+|externo))\b", normalized)
    if (monitor_destination
            and re.search(r"\b(?:mova|mover|coloque|colocar|envie|enviar)\b", normalized)
            and re.search(r"\b(?:janela|firefox|chrome|vscode|vs code|"
                          r"terminal|ptyxis|code)\b", normalized)
            and not re.search(r"\b(?:depois|em seguida|tambem|por fim)\b", normalized)):
        return [t for t in available if t.get("name") == "move_window_to_monitor"]
    workspace_target = re.search(r"\b(?:area(?:s)? de trabalho|workspace(?:s)?)\b", normalized)
    if workspace_target and not re.search(r"\b(?:e depois|em seguida|tambem|por fim)\b", normalized):
        if (re.search(r"\b(?:mova|mover|coloque|colocar|envie|enviar)\b", normalized)
                and re.search(r"\b(?:janela|firefox|chrome|vscode|vs code|"
                              r"terminal|ptyxis|code)\b", normalized)):
            return [t for t in available if t.get("name") == "move_window_to_workspace"]
        if (re.search(r"\b(?:ative|ativar|altere|alterar|troque|trocar|"
                      r"mude|mudar|va para|ir para)\b", normalized)
                and not re.search(r"\b(?:janela|firefox|chrome|vscode|vs code|"
                                  r"terminal|ptyxis|code)\b", normalized)):
            return [t for t in available if t.get("name") == "activate_workspace"]
    if (re.search(r"\b(?:monitores?|workspaces?|areas? de trabalho)\b", normalized)
            and re.search(r"\b(?:quais?|quantos?|liste|listar|mostre|mostrar|"
                          r"identifique|identificar|em qual)\b", normalized)
            and not re.search(r"\b(?:mova|mover|coloque|colocar|troque|trocar|"
                              r"altere|alterar|abra|abrir|feche|fechar|depois|"
                              r"tambem)\b", normalized)):
        return [t for t in available if t.get("name") == "desktop_spaces"]
    if (re.search(r"\b(?:historico|acoes anteriores|operacoes anteriores)\b", normalized)
            and re.search(r"\b(?:janela|janelas|layout)\b", normalized)):
        return [t for t in available if t.get("name") == "window_action_history"]
    if re.search(r"\b(?:perfil|layout)\b", normalized):
        if re.search(r"\b(?:restaure|restaurar|recupere|recuperar)\b", normalized):
            return [t for t in available if t.get("name") == "restore_window_layout"]
        if re.search(r"\b(?:salve|salvar|guarde|guardar)\b", normalized):
            return [t for t in available if t.get("name") == "save_window_layout"]
        if re.search(r"\b(?:liste|listar|mostre|mostrar|quais)\b", normalized):
            return [t for t in available if t.get("name") == "list_window_layouts"]
    # Layout declarativo: o posicionamento usa só ferramentas GNOME.
    # Não trata "mova um arquivo" como janela; mantém o catálogo completo.
    layout_target = re.search(r"\b(?:janela|janelas|firefox|chrome|"
                              r"vscode|vs code|terminal|ptyxis|code)\b", normalized)
    if layout_target and re.search(r"\b(?:tres|quatro|3|4)\s+janelas\b", normalized):
        return [t for t in available if t.get("name") == "arrange_window_grid"]
    if layout_target and (re.search(r"\b(?:metade|lado a lado|centro|centralize|"
                                    r"esquerda|direita|canto|divida a tela)\b", normalized)
                          or re.search(r"\b\d{1,3}%", normalized)
                          or re.search(r"\bx\s*=\s*\d+", normalized)):
        if ("lado a lado" in normalized or re.search(
                r"\b(?:firefox|chrome|vscode|vs code|terminal|ptyxis|code)\s+"
                r"(?:e|com)\s+(?:firefox|chrome|vscode|vs code|terminal|ptyxis|code)\b",
                normalized)):
            return [t for t in available if t.get("name") == "arrange_windows"]
        if re.search(r"\b(?:coloque|colocar|mova|mover|posicione|"
                     r"posicionar|organize|organizar|centralize|deixe|ocupe)\b", normalized):
            return [t for t in available if t.get("name") == "place_window"]

    if (re.search(r"\b(?:feche|fechar)\b", normalized)
            and re.search(r"\b(?:janela|firefox|chrome|vscode|code|terminal|ptyxis)\b", normalized)
            and not re.search(r"\b(?: e |depois|em seguida|tambem|todas|todos)\b", normalized)):
        return [t for t in available if t.get("name") == "close_window"]

    if (re.search(r"\b(?:qual|que|mostre|mostrar|identifique)\b", normalized)
            and re.search(r"\b(?:janela|aplicativo)\b", normalized)
            and re.search(r"\b(?:em foco|primeiro plano|ativa)\b", normalized)
            and not re.search(r"\b(?: e |depois|em seguida|tambem)\b", normalized)):
        return [t for t in available if t.get("name") == "focused_window"]

    # Não escolher só uma ferramenta se houve pedido de arquivo, navegador,
    # abertura de aplicativo, mais de uma ação ou operação composta.
    complex_verbs = (r"\b(?:abra|abrir|inicie|iniciar|crie|criar|"
                     r"salve|salvar|escreva|escrever|edite|editar|"
                     r"feche|fechar|mova|mover|apague|apagar|"
                     r"clique|clicar|pesquise|pesquisar|"
                     r"navegue|navegar|acesse|acessar)\b")
    complex_targets = r"\b(?:arquivo|arquivos|pasta|pastas|projeto|projetos|site|sites)\b"
    if re.search(complex_verbs, normalized) or re.search(complex_targets, normalized):
        return available
    if re.search(r"\b(?:depois|em seguida|por fim|tambem)\b", normalized):
        return available

    # Comandos simples de estado de janela: o próprio manage_window seleciona
    # por classe/título e faz a revalidação, sem inventário LLM adicional.
    if (re.search(r"\b(?:minimize|minimizar|maximize|maximizar|"
                  r"restaure|restaurar|desmaximize|desmaximizar)\b", normalized)
            and re.search(r"\b(?:janela|firefox|chrome|vscode|code|"
                          r"terminal|ptyxis|aplicativo)\b", normalized)
            and not re.search(r"\b(?:liste|listar|mostre|mostrar|quais|"
                              r"todas|todos|outras|varias)\b", normalized)):
        return [t for t in available if t.get("name") == "manage_window"]

    # Solicitações únicas de foco (identificar a janela é parte interna do
    # focus_window); uma consulta adicional ao desktop não é necessária.
    focus_verb = re.search(
        r"\b(?:coloque|colocar|traga|trazer|ative|ativar|foque|focar)\b",
        normalized,
    )
    focus_target = re.search(
        r"\b(?:primeiro plano|em foco|janela|janelas)\b",
        normalized,
    )
    if focus_verb and focus_target and not re.search(
        r"\b(?:liste|listar|mostre|mostrar|quais|todas|todos)\b", normalized
    ):
        return [t for t in available if t.get("name") == "focus_window"]

    # Leitura simples de janelas disponíveis. Não confundir com ações de foco.
    if re.search(r"\b(?:janelas|janela)\b", normalized) and re.search(
        r"\b(?:quais|liste|listar|mostre|mostrar|veja|ver|abertas|abertos)\b",
        normalized,
    ) and not focus_verb:
        return [t for t in available if t.get("name") == "desktop_windows"]

    return available
