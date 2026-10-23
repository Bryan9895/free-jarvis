"""Serviço de aplicação compartilhado por CLI, GUI e futuras interfaces de voz."""
from __future__ import annotations

import os
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


class JarvisService:
    def __init__(self, client, agent, toolkit, memory, planner, approval, *, report=print):
        self.client = client
        self.agent = agent
        self.toolkit = toolkit
        self.memory = memory
        self.planner = planner
        self.approval = approval
        self._lock = Lock()
        self._current_token = None
        self.tasks = NaturalTaskController(planner, approval, report=report,
                                           cancel_token_provider=lambda: self._current_token)

    @classmethod
    def from_config(cls, config, *, manual_callback=None, auto=True, report=print):
        approval = ApprovalPolicy(auto=auto, manual_callback=manual_callback, report=report)
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
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Já há uma tarefa em execução")
        token = CancellationToken()
        self._current_token = token
        try:
            answer = self.tasks.handle(message)
            if answer is None:
                answer = self.agent.ask(message, cancel_token=token)
            return answer
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
