"""Endpoint limitado por amostras; não confunde espera com duração da fala.

Recebe decisões de atividade do adaptador. RMS legado é um fallback de nível,
não um VAD acústico validado. Nenhum texto parcial deve sair de um erro aqui.
"""
from collections import deque
from math import ceil


class TurnLimitError(RuntimeError):
    pass


class AudioEndpoint:
    def __init__(self, sample_rate, *, silence_seconds=1.0, max_seconds=120,
                 preroll_seconds=0.8, chunk_sink=None):
        if sample_rate <= 0 or silence_seconds <= 0 or max_seconds <= silence_seconds:
            raise ValueError("Configuração de endpoint inválida")
        self.rate = sample_rate
        self.silence_limit = ceil(silence_seconds * sample_rate)
        self.limit = ceil(max_seconds * sample_rate)
        self.preroll_limit = ceil(preroll_seconds * sample_rate)
        self.recent = deque()
        self.recent_samples = 0
        self.chunks = []
        self.samples = 0
        self.quiet = 0
        self.started = False
        self.chunk_sink = chunk_sink

    def store_chunk(self, chunk):
        if self.chunk_sink is not None:
            self.chunk_sink(chunk)
        else:
            self.chunks.append(chunk)

    def feed(self, chunk, active):
        """Retorna True apenas após silêncio completo; teto sempre levanta erro."""
        size = len(chunk)
        if not self.started:
            self.recent.append(chunk)
            self.recent_samples += size
            while len(self.recent) > 1 and self.recent_samples - len(self.recent[0]) >= self.preroll_limit:
                self.recent_samples -= len(self.recent.popleft())
            if not active:
                return False
            self.started = True
            for frame in self.recent:
                self.store_chunk(frame)
            self.samples = self.recent_samples
            self.recent.clear()
        else:
            self.store_chunk(chunk)
            self.samples += size
        self.quiet = 0 if active else self.quiet + size
        if self.samples >= self.limit:
            self.chunks.clear()
            raise TurnLimitError("Limite de segurança de áudio atingido; pedido não enviado. Repita em partes.")
        return self.quiet >= self.silence_limit
