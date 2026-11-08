"""Janela móvel de métricas sem gravar textos, áudio ou segredos."""
from collections import deque
from .latency import summary


class LatencyHistory:
    def __init__(self, max_turns=60):
        if type(max_turns) is not int or not 1 <= max_turns <= 1000:
            raise ValueError("Amostras fora de intervalo")
        self.total_ms = deque(maxlen=max_turns)
        self.first_text_ms = deque(maxlen=max_turns)

    def add(self, total_ms, first_text_ms=None):
        if type(total_ms) not in (int, float) or total_ms < 0:
            raise ValueError("Duração inválida")
        if first_text_ms is not None:
            if type(first_text_ms) not in (int, float) or not 0 <= first_text_ms <= total_ms:
                raise ValueError("Primeiro texto fora do turno")
        self.total_ms.append(float(total_ms))
        if first_text_ms is not None:
            self.first_text_ms.append(float(first_text_ms))

    def snapshot(self):
        return {"turn": summary(self.total_ms),
                "first_text": summary(self.first_text_ms)}
