"""Resolução local somente de comandos com estrutura inequívoca."""
import re
from .router import compound_request


def task_add_intent(message, available):
    if '\n' in message or compound_request(message):
        return None
    if not any(spec.get('name') == 'task_add' for spec in available):
        return None
    text = re.sub(r'^\s*jarvis[,.:!\s]+', '', message, flags=re.I)
    match = re.fullmatch(r'\s*adicione\s+(?:às|as|nas)\s+(?:minhas\s+)?tarefas\s*:\s*(.+?)\s*', text, flags=re.I)
    if not match:
        return None
    title = match[1].strip()
    if re.search(r'\bprioridade\b', title, re.I):
        return None
    title = title.rstrip('.').strip()
    if title[:1] in ('"', "'", '“'):
        ending = {'"': '"', "'": "'", '“': '”'}[title[0]]
        if not title.endswith(ending):
            return None
        title = title[1:-1].strip()
    if not title or len(title) > 500:
        return None
    return {'title': title, 'priority': 2}
