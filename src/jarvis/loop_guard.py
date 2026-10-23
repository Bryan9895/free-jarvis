"""Detecta repetição de chamadas de ferramenta dentro de um pedido."""
from collections import deque


class LoopGuard:
    def __init__(self):
        self._recent = deque(maxlen=6)

    def observe(self, signature) -> bool:
        self._recent.append(signature)
        recent = list(self._recent)
        if len(recent) >= 3 and recent[-3] == recent[-2] == recent[-1]:
            return True
        if len(recent) == 6 and recent[:2] * 3 == recent and recent[0] != recent[1]:
            return True
        return False
