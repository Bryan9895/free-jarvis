"""Interpretação local e conservadora de intenções para tarefas persistentes.

Sem chamada extra ao FCC para identificar intenções claras. Perguntas usuais
seguem para o agente rápido. Operações incertas nunca são repetidas sozinhas.
"""
from __future__ import annotations

import re
import unicodedata

_STOP = frozenset(
    "a o as os um uma de do da dos das e em no na nos nas meu minha meus minhas "
    "seu sua seus suas projeto tarefa tarefas trabalho favor jarvis por para com "
    "que eu voce voce aonde onde os pasta pastas analise analisa "
    "analisar continue continuar retome retomar estava estavamos paramos parei "
    "parou sobre".split()
)

_MULTI = re.compile(
    r"\b(?:e depois|em seguida|depois disso|por fim|primeiro|segundo|terceiro)\b"
)
_VERBS = re.compile(
    r"\b(?:abra|abrir|liste|listar|leia|ler|encontre|encontrar|identifique|"
    r"identificar|resuma|resumir|analise|analisar|verifique|verificar|"
    r"escreva|escrever|crie|criar|edite|editar|acesse|acessar|"
    r"pesquise|pesquisar|organize|organizar|explique|explicar)\b"
)
_TASK_TARGET = re.compile(
    r"\b(?:arquivo|arquivos|pasta|pastas|workspace|projeto|repositorio|"
    r"navegador|janela|desktop|diretorio|git|site|pagina|computador)\b"
)


def normalize(value):
    value = unicodedata.normalize("NFKD", value.lower())
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def keywords(value):
    return {word for word in re.findall(r"[a-z0-9]+", normalize(value))
            if len(word) >= 3 and word not in _STOP}


def classify(message):
    """history/status/resume/resolve_skip/resolve_retry/execute/cancel/plan/normal."""
    raw = normalize(message.strip())
    raw = re.sub(r"^[,\s]*(?:jarvis[,\s]+)?", "", raw)
    if not raw or message.lstrip().startswith("/"):
        return "normal"
    if re.search(r"\b(?:historico|anteriores|antigas)\b.*\b(?:tarefas|planos)\b|"
                 r"\b(?:tarefas|planos)\b.*\b(?:anteriores|antigas|historico)\b", raw):
        return "history"
    if re.search(r"\b(?:mostre|mostrar|veja|ver|status|progresso|andamento|"
                 r"como esta|qual o estado)\b.*\b(?:plano|tarefa)\b|"
                 r"\b(?:meu plano|plano atual|tarefa atual)\b", raw):
        return "status"
    if re.search(r"\b(?:ignore|ignorar|pule|pular|deixe de lado)\b.*"
                 r"\b(?:etapa|passo|pendente|anterior|interrompid)", raw):
        return "resolve_skip"
    if re.search(r"\b(?:repita|repetir|refaca|refazer|tente novamente)\b.*"
                 r"\b(?:etapa|passo|interrompid)", raw):
        return "resolve_retry"
    if re.search(r"\b(?:continue|continuar|retome|retomar|prossiga|"
                 r"de onde parou|onde paramos)\b", raw):
        return "resume"
    if re.search(r"\b(?:cancele|cancelar|desista)\b.*\b(?:plano|tarefa)\b", raw):
        return "cancel"
    if re.search(r"\b(?:execute|executar|inicie|iniciar|comece|comecar)\b.*"
                 r"\b(?:plano|etapas|tarefa planejada)\b", raw):
        return "execute"
    if re.search(r"\b(?:planeje|planejar|monte um plano|crie um plano)\b", raw):
        return "plan"
    # Só planejar automaticamente sequências expressas com múltiplas operações
    # sobre recursos locais; frases comuns continuam sendo respondidas pelo agente.
    if _TASK_TARGET.search(raw) and (_MULTI.search(raw) or len(_VERBS.findall(raw)) >= 2):
        return "plan_execute"
    return "normal"


def find_relevant(plans, request):
    """Correspondência lexical restrita; na ambiguidade não escolhe."""
    words = keywords(request)
    scored = []
    for plan in plans:
        if plan.get("status") not in ("ready", "stopped", "interrupted"):
            continue
        goal_words = keywords(plan.get("goal", ""))
        overlap = len(words & goal_words)
        if overlap >= 1 and (overlap >= 2 or len(words) <= 2):
            scored.append((overlap, plan))
    scored.sort(key=lambda entry: (entry[0], entry[1].get("id", 0)), reverse=True)
    if not scored:
        return None, []
    best_score = scored[0][0]
    matches = [p for score, p in scored if score == best_score]
    if len(matches) != 1:
        return None, matches
    return matches[0], []
