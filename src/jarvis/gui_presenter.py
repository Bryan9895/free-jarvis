"""Apresentação da GUI em português, sem depender de Tk nem do modelo."""
LABELS = {
    'no_plan': 'Sem plano', 'ready': 'Pronto para executar', 'running': 'Em execução',
    'pending': 'Pendente', 'in_progress': 'Em andamento', 'done': 'Concluída',
    'verified': 'Verificada', 'completed_verified': 'Todas as etapas verificadas',
    'completed_unverified': 'Concluído com resultados não verificados',
    'reported_unverified': 'Resultado não verificado', 'stopped': 'Parado; confira a etapa',
    'interrupted': 'Interrompido; confira os efeitos', 'cancelled': 'Cancelado',
    'failed': 'Falhou', 'blocked': 'Bloqueada', 'skipped_unverified': 'Ignorada; não verificada',
    'rejected': 'Operação recusada', 'not_found': 'Alvo não encontrado',
    'ambiguous': 'Mais de um alvo; informe o título', 'unavailable': 'Recurso indisponível',
    'state_verified': 'Estado confirmado', 'geometry_verified': 'Posição confirmada',
    'layout_verified': 'Organização confirmada', 'closed_verified': 'Fechamento confirmado',
    'close_unverified': 'Fechamento ainda não confirmado', 'loaded': 'Página carregada',
    'observed': 'Estado observado', 'listed': 'Lista atualizada',
}


def status_label(status):
    return LABELS.get(status, f'Estado informado: {status}')


def error_message(error):
    text = str(error)
    lowered = text.casefold()
    if 'http 404' in lowered and '/v1/responses' in lowered:
        return ('O modelo de conversa não está disponível (HTTP 404). '
                'Abra Modelos, atualize o catálogo e selecione outro modelo. '
                'Seu pedido não recebeu resposta; o erro não é do microfone.')
    if '/v1/responses' in lowered and ('http 401' in lowered or 'http 403' in lowered):
        return 'A API recusou o acesso ao modelo. Confira as credenciais do FCC e as permissões do provedor.'
    if '/v1/responses' in lowered and 'http 429' in lowered:
        return 'O provedor atingiu o limite de uso. Aguarde ou selecione outro modelo em Modelos.'
    return text[:800]


def plan_progress(plan):
    steps = plan.get('steps', [])
    return sum(step.get('status') == 'verified' for step in steps), len(steps)


def plan_details(plan):
    lines = []
    if plan.get('goal'):
        lines.append('Objetivo: ' + plan['goal'])
    for step in plan.get('steps', []):
        lines.append(f"Etapa {step.get('id')}: {step.get('description', '')}\n"
                     f"{status_label(step.get('status', 'pending'))}")
        for issue in step.get('problems', []):
            lines.append(str(issue.get('reason', 'Falha sem detalhe'))[:500])
        if step.get('result'):
            lines.append(str(step['result'])[:700])
    return '\n\n'.join(lines) or 'Crie ou selecione um plano para acompanhar as etapas.'


def action_summary(detail):
    text = status_label(detail.get('status', 'desconhecido'))
    if detail.get('task_id') is not None:
        text += f" · tarefa #{detail['task_id']}"
    if detail.get('tab_id') is not None:
        text += f" · aba #{detail['tab_id']}"
    if detail.get('reason'):
        text += '\n' + str(detail['reason'])[:500]
    return text
