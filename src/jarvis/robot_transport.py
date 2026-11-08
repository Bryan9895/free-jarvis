"""Contrato local e testável para futura ponte serial Adam/ESP32.

Não cria conexão de rede, não abre porta serial automaticamente e não aciona
motores. Um Orange Pi poderá controlar a ponte após consentimento explícito.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

MAX_FRAME_BYTES = 512
SAFE_COMMANDS = frozenset(("ping", "led", "status", "sensor_read"))


@dataclass(frozen=True)
class RobotPacket:
    action: str
    value: object = None

    def encode(self) -> bytes:
        if not isinstance(self.action, str) or self.action not in SAFE_COMMANDS:
            raise ValueError("Comando de periférico desconhecido ou não permitido")
        if self.action == "led" and self.value not in (0, 1, False, True):
            raise ValueError("LED exige valor 0 ou 1")
        if self.action == "sensor_read" and (not isinstance(self.value, str)
                                             or not self.value.isidentifier()
                                             or len(self.value) > 32):
            raise ValueError("Nome de sensor inválido")
        if self.action in ("ping", "status") and self.value is not None:
            raise ValueError("Esse comando não aceita valor")
        payload = json.dumps({"v": 1, "action": self.action, "value": self.value},
                             ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n"
        if len(payload) > MAX_FRAME_BYTES:
            raise ValueError("Comando excedeu orçamento de bytes")
        return payload

    @classmethod
    def decode(cls, raw: bytes):
        if len(raw) > MAX_FRAME_BYTES or not raw.endswith(b"\n"):
            raise ValueError("Quadro incompleto ou muito grande")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise ValueError("Quadro JSON inválido") from exc
        if not isinstance(data, dict) or set(data) != {"v", "action", "value"} or data["v"] != 1:
            raise ValueError("Protocolo de robô incompatível")
        item = cls(data["action"], data["value"])
        item.encode()  # revalida também no recebimento
        return item


class RobotTransport(Protocol):
    def request(self, packet: RobotPacket) -> RobotPacket: ...


class SimulatedRobot:
    """Simulador sem hardware, nenhum atuador real é invocado."""
    def __init__(self):
        self.led_on = False

    def request(self, packet: RobotPacket) -> RobotPacket:
        packet = RobotPacket.decode(packet.encode())
        if packet.action == "led":
            self.led_on = bool(packet.value)
            return RobotPacket("status")
        if packet.action == "sensor_read":
            return RobotPacket("status")
        return RobotPacket("status")
