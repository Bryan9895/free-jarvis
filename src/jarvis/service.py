"""Serviço de aplicação compartilhado por CLI, GUI e futuras interfaces de voz."""
from __future__ import annotations

import os
import math
from time import monotonic
from threading import Lock

from .agent import Agent
from .approval import ApprovalPolicy
from .cancellation import CancellationToken
from .fcc import FCCClient, AutoModelClient
from .memory import Memory
from .natural_tasks import NaturalTaskController
from .plan_store import PlanStore
from .planner import TaskPlanner
from .plugins import load_plugins
from .registry import CapabilityPolicy
from .tools import DEFAULT_REGISTRY, Toolkit


def _turn_token(existing=None):
    try:
        seconds = float(os.getenv('JARVIS_TURN_TIMEOUT', '120'))
    except ValueError as exc:
        raise ValueError('JARVIS_TURN_TIMEOUT deve ser um número entre 1 e 3600 segundos') from exc
    if not math.isfinite(seconds) or not 1 <= seconds <= 3600:
        raise ValueError('JARVIS_TURN_TIMEOUT deve estar entre 1 e 3600 segundos')
    from .latency import current_trace
    trace = current_trace()
    enqueued = [] if trace is None else [event['at'] for event in trace.snapshot()['events']
                                       if event['stage'] == 'intent_enqueued']
    deadline = (enqueued[0] if enqueued else monotonic()) + seconds
    token = existing or CancellationToken()
    token.deadline = min(token.deadline, deadline) if token.deadline is not None else deadline
    return token


class JarvisService:
    supports_turn_cancellation = True
    def __init__(self, client, agent, toolkit, memory, planner, approval, *, report=print):
        self.client = client
        self.agent = agent
        self.toolkit = toolkit
        self.memory = memory
        self.planner = planner
        self.approval = approval
        self._lock = Lock()
        self._current_token = None
        self._report = report
        self.tasks = NaturalTaskController(planner, approval, report=report,
                                           cancel_token_provider=lambda: self._current_token)

    @classmethod
    def from_config(cls, config, *, manual_callback=None, auto=True, report=print):
        from .authorizations import AuthorizationStore
        authorizations = AuthorizationStore()
        if authorizations.error:
            report('Concessões não carregadas: ' + authorizations.error)
        approval = ApprovalPolicy(auto=auto, manual_callback=manual_callback, report=report,
                                  authorizations=authorizations)
        raw = FCCClient(config.url, config.token)
        client = AutoModelClient(raw, preferred=config.model,
                                 backups=[x.strip() for x in os.getenv(
                                     "FCC_FALLBACK_MODELS", "").split(",") if x.strip()],
                                 allow_cross_provider=os.getenv(
                                     "FCC_ALLOW_CROSS_PROVIDER", "") == "1")
        client.initialize()
        memory = Memory(config.db)
        toolkit = None
        store = None
        try:
            registry = load_plugins(DEFAULT_REGISTRY, os.getenv("JARVIS_PLUGINS", ""))
            toolkit = Toolkit(config.workspace, approve=approval, layout_db=config.db,
                              registry=registry)
            agent = Agent(client, toolkit, memory, client.active_model)
            store = PlanStore(config.db)
            planner = TaskPlanner(client, agent, store=store)
            return cls(client, agent, toolkit, memory, planner, approval, report=report)
        except Exception:
            if store is not None:
                store.close()
            if toolkit is not None:
                toolkit.close()
            memory.close()
            raise

    def ask(self, message: str) -> str:
        return self.ask_stream(message)

    def ask_stream(self, message: str, *, on_text=None, cancel_token=None) -> str:
        token = _turn_token(cancel_token)
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Já há uma tarefa em execução")
        self._current_token = token
        try:
            token.check()
            answer = self.tasks.handle(message)
            if answer is None:
                if on_text is None:
                    answer = self.agent.ask(message, cancel_token=token)
                else:
                    answer = self.agent.ask(message, cancel_token=token, on_text=on_text)
            return answer
        finally:
            self._current_token = None
            self._lock.release()

    def plan_action(self, action, value=None):
        """Mesma exclusão/cancelamento do chat para os controles diretos de plano."""
        if action not in {"prepare", "execute", "select", "resume", "resolve", "cancel"}:
            raise ValueError("Ação de plano desconhecida")
        token = _turn_token()
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Já há uma tarefa em execução")
        self._current_token = token
        try:
            token.check()
            if action == "prepare":
                result = self.planner.prepare(value, cancel_token=token)
            elif action == "execute":
                result = self.planner.execute(self.approval, report=self._report, cancel_token=token)
            elif action == "select":
                if type(value) is not int or value < 1:
                    raise ValueError("ID de plano inválido")
                result = self.planner.select(value)
            elif action == "resume":
                result = self.planner.ready_to_resume()
            elif action == "cancel":
                result = self.planner.cancel()
            else:
                if value not in ("skip", "retry"):
                    raise ValueError("Escolha skip ou retry")
                snapshot = self.planner.snapshot()
                step = next((item for item in snapshot.get("steps", []) if item.get("status")
                             in ("interrupted", "failed", "blocked", "running")), None)
                if step is None:
                    raise ValueError("Nenhuma etapa incerta")
                confirmation = getattr(self.approval, "confirm_sensitive", self.approval)
                if not confirmation(f"RESOLVER etapa #{step['id']} ({step['description']}) "
                                    f"como {value}? Confira efeitos antes de repetir."):
                    return snapshot
                result = self.planner.resolve_step(value)
            token.check()
            return result
        finally:
            self._current_token = None
            self._lock.release()

    def cancel_current(self) -> bool:
        token = self._current_token
        if token is None:
            return False
        token.cancel()
        return True

    def set_capabilities(self, enabled: set[str]):
        if self._lock.locked():
            raise RuntimeError("Altere capacidades após terminar a tarefa atual")
        self.toolkit.capabilities = CapabilityPolicy(self.toolkit.registry, enabled)

    def close(self):
        self.cancel_current()
        if self._lock.locked():
            raise RuntimeError("Aguarde a tarefa em execução terminar")
        self.toolkit.close()
        if self.planner.store is not None:
            self.planner.store.close()
        self.memory.close()
