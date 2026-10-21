"""Apresentação legível de planos no terminal, sem JSON bruto."""
from datetime import datetime


_LABELS = {
    "ready": "Pronto para executar",
    "running": "Em execução",
    "completed_unverified": "Etapas processadas (sem verificação independente)",
    "stopped": "Interrompido por erro ou bloqueio",
    "cancelled": "Cancelado",
    "interrupted": "Interrompido ao encerrar a JARVIS",
    "pending": "Pendente",
    "reported_unverified": "Processada; resultado não verificado",
    "blocked": "Bloqueada",
    "failed": "Falhou",
}


def format_plan(plan, *, show_results=True):
    if not plan or plan.get("status") == "no_plan":
        return "Nenhum plano encontrado. Use /planejar <objetivo>."
    steps = plan.get("steps", [])
    completed = sum(s.get("status") == "reported_unverified" for s in steps)
    total = len(steps)
    width = 22
    progress = round(width * completed / total) if total else 0
    bar = "█" * progress + "░" * (width - progress)
    created = datetime.fromtimestamp(plan["created_at"]).strftime("%d/%m/%Y %H:%M") if plan.get("created_at") else "—"
    lines = [
        "",
        "╔══════════════════ JARVIS • PLANO DE TAREFA ══════════════════",
        f"  Objetivo: {plan.get('goal','—')}",
        f"  Identificador: #{plan.get('id', 'temporário')}  |  Criado: {created}",
        f"  Modelo: {plan.get('model', '—')}",
        f"  Situação: {_LABELS.get(plan.get('status'), plan.get('status','—'))}",
        f"  Progresso: [{bar}] {completed}/{total} etapas",
        "  " + "─" * 55,
    ]
    symbols = {"pending": "○", "running": "◌", "reported_unverified": "✓",
               "failed": "✕", "blocked": "!", "interrupted": "!",}
    for step in steps:
        status = step.get("status", "pending")
        lines.append(f"  {symbols.get(status, '·')} {step.get('id','?')}. {step.get('description','—')}")
        lines.append(f"     {_LABELS.get(status, status)}")
        if show_results and step.get("result"):
            excerpt = " ".join(str(step["result"]).split())
            lines.append(f"     ↳ {excerpt[:220]}{'…' if len(excerpt) > 220 else ''}")
        if show_results and step.get("problems"):
            for issue in step["problems"][:3]:
                lines.append(f"     ⚠ {issue.get('tool','ferramenta')}: {issue.get('reason','erro')}")
    lines.extend([
        "  " + "─" * 55,
        "  /executar-plano • /cancelar-plano • /historico-planos",
        "  ✓ significa etapa processada; não é confirmação externa de êxito.",
        "╚" + "═" * 62,
    ])
    return "\n".join(lines)


def format_history(plans):
    if not plans:
        return "Nenhum plano salvo no histórico."
    lines = ["", "JARVIS • HISTÓRICO DE PLANOS", "─" * 66]
    for plan in plans:
        steps = plan.get("steps", [])
        processed = sum(s.get("status") == "reported_unverified" for s in steps)
        state = _LABELS.get(plan.get("status"), plan.get("status","—"))
        lines.append(f"  #{plan.get('id','?')}  {plan.get('goal','—')[:65]}")
        lines.append(f"       {state}  •  {processed}/{len(steps)} etapas")
    return "\n".join(lines)
