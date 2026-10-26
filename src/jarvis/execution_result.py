"""Estados gerais de execução sobre os estados específicos das ferramentas.

O mapeamento é conservador: um estado novo ou desconhecido nunca vira sucesso
verificado automaticamente. Não depende de texto narrativo do modelo.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResultState(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


_VERIFIED = frozenset({
    "verified", "focused_verified", "already_focused", "state_verified",
    "already_in_state", "geometry_verified", "layout_verified",
    "workspace_verified", "window_workspace_verified", "window_monitor_verified",
    "profile_verified", "closed_verified", "observed", "window_observed",
    "listed", "loaded", "filled_verified", "screenshot_verified",
})
_APPLIED = frozenset({"written", "created", "moved", "trashed"})
_REJECTED = frozenset({"rejected", "cancelled", "not_attempted"})
_NOT_FOUND = frozenset({"not_found", "not_observed", "content_mismatch"})
_FAILED = frozenset({"failed", "refused", "not_activated", "changed"})
_PARTIAL = frozenset({"profile_partial"})
_SENT = frozenset({"launched_unverified", "sent_unverified", "opened_unverified",
                   "execution_uncertain",
                   "launch_uncertain", "close_unverified", "state_unverified",
                   "focus_unverified", "geometry_unverified", "layout_unverified",
                   "workspace_unverified", "window_workspace_unverified",
                   "window_monitor_unverified", "executed"})


@dataclass(frozen=True)
class ExecutionResult:
    state: ResultState
    raw_status: str
    effect_sent: bool = False

    @property
    def retry_safe(self) -> bool:
        return not self.effect_sent and self.state in {
            ResultState.REJECTED, ResultState.NOT_FOUND, ResultState.AMBIGUOUS,
            ResultState.UNAVAILABLE,
        }

    def as_dict(self) -> dict:
        return {"state": self.state.value, "raw_status": self.raw_status,
                "effect_sent": self.effect_sent, "retry_safe": self.retry_safe}


def classify_tool_outcome(outcome: dict, *, capability: str = "") -> ExecutionResult:
    """Classifica envelope {result|error}, mantendo o estado legado para diagnóstico."""
    if not isinstance(outcome, dict):
        return ExecutionResult(ResultState.FAILED, "invalid_envelope")
    if outcome.get("error") is not None:
        return ExecutionResult(ResultState.FAILED, "error")
    detail = outcome.get("result")
    status = detail.get("status") if isinstance(detail, dict) else None
    verification = outcome.get("verification")
    if (isinstance(verification, dict) and verification.get("status") == "verified"
            and status is not None):
        return ExecutionResult(ResultState.VERIFIED, status, effect_sent=True)
    if status in _REJECTED:
        return ExecutionResult(ResultState.REJECTED, status)
    if status == "unavailable":
        return ExecutionResult(ResultState.UNAVAILABLE, status)
    if status in _NOT_FOUND:
        return ExecutionResult(ResultState.NOT_FOUND, status)
    if status == "ambiguous":
        return ExecutionResult(ResultState.AMBIGUOUS, status)
    if status in _FAILED:
        return ExecutionResult(ResultState.FAILED, status,
                               effect_sent=capability in ('command.execute', 'system.admin'))
    if status in _PARTIAL:
        return ExecutionResult(ResultState.PARTIAL, status, effect_sent=True)
    if status in _SENT or status in _APPLIED:
        return ExecutionResult(ResultState.UNVERIFIED, status, effect_sent=True)
    if status == "saved":
        return ExecutionResult(ResultState.VERIFIED if capability == "desktop.control"
                               else ResultState.UNVERIFIED, status,
                               effect_sent=capability != "desktop.control")
    if status in _VERIFIED:
        return ExecutionResult(ResultState.VERIFIED, status)
    if status is None and capability.endswith(".read"):
        if isinstance(detail, dict) and isinstance(detail.get("exit_code"), int):
            return ExecutionResult(ResultState.VERIFIED if detail["exit_code"] == 0
                                   else ResultState.FAILED, "command_exit")
        if "result" in outcome:
            return ExecutionResult(ResultState.VERIFIED, "read_returned")
    return ExecutionResult(ResultState.UNVERIFIED,
                           str(status) if status is not None else "unknown")
