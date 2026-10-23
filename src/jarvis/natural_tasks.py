"""Conversa natural conectada ao planejador, histórico e execução supervisionada."""
from .task_intent import classify, find_relevant, keywords
from .plan_view import format_plan, format_history


class NaturalTaskController:
    def __init__(self, planner, approve, report=print, cancel_token_provider=None):
        self.planner = planner
        self.approve = approve
        self.report = report
        self.cancel_token_provider = cancel_token_provider or (lambda: None)

    def _execute(self):
        return self.planner.execute(self.approve, report=self.report,
                                    cancel_token=self.cancel_token_provider())

    def _show(self, plan):
        return format_plan(plan)

    def _continue(self, message):
        plans = self.planner.history(30)
        target, ambiguous = find_relevant(plans, message)
        if ambiguous:
            entries = "\n".join(
                f"  #{p.get('id')} — {p.get('goal', '')[:110]}"
                for p in ambiguous[:8]
            )
            return (
                "Encontrei várias tarefas possíveis e não vou escolher por conta própria:\n"
                + entries + "\nInforme o número ou descreva melhor a tarefa."
            )
        current = self.planner.snapshot()
        if target is None:
            if keywords(message):
                return "Não encontrei plano correspondente ao assunto; indique o identificador do histórico."
            if current.get("status") in ("ready", "stopped", "interrupted"):
                target = current
            else:
                available = [p for p in plans
                             if p.get("status") in ("ready", "stopped", "interrupted")]
                if len(available) == 1:
                    target = available[0]
                elif len(available) > 1:
                    return (
                        "Há várias tarefas pausadas. Indique o assunto ou número da tarefa:\n"
                        + format_history(available[:5])
                    )
                else:
                    return "Não encontrei tarefa pendente ou interrompida para continuar."
        if current.get("id") != target.get("id"):
            self.planner.select(target["id"])
        state = self.planner.snapshot()
        if state["status"] in ("stopped", "interrupted"):
            uncertain = [s for s in state["steps"]
                         if s["status"] in ("interrupted", "failed", "blocked", "running")]
            if uncertain:
                first = uncertain[0]
                return (
                    self._show(state)
                    + "\nA etapa " + str(first["id"]) + " tem resultado incerto. "
                    "Confira o estado real antes de decidir. "
                    "Você pode dizer 'ignore a etapa interrompida' para pular ou "
                    "'repita a etapa interrompida' para colocá-la na fila. "
                    "Não repetirei automaticamente."
                )
            try:
                self.planner.ready_to_resume()
            except ValueError as exc:
                return str(exc)
        state = self.planner.snapshot()
        if state["status"] == "ready":
            return self._show(self._execute())
        return self._show(state)

    def handle(self, message):
        """Retorna None se não for uma intenção de tarefa; caso contrário, resposta."""
        kind = classify(message)
        if kind == "normal":
            return None
        if kind == "history":
            return format_history(self.planner.history())
        if kind == "status":
            return self._show(self.planner.snapshot())
        if kind == "cancel":
            return self._show(self.planner.cancel())
        if kind == "execute":
            return self._show(self._execute())
        if kind in ("resolve_skip", "resolve_retry"):
            choice = "skip" if kind == "resolve_skip" else "retry"
            state = self.planner.snapshot()
            uncertain = next(
                (s for s in state.get("steps", [])
                 if s.get("status") in ("interrupted", "failed", "blocked", "running")), None
            )
            if not uncertain:
                return "Não há etapa incerta para resolver."
            message = (f"RESOLVER etapa #{uncertain['id']}: "
                       f"{uncertain['description']} como {choice}?")
            if not self.approve(message):
                return "Decisão cancelada. O plano não foi alterado."
            return self._show(self.planner.resolve_step(choice)) + (
                "\nQuando quiser continuar, diga 'continue de onde parou'."
            )
        if kind == "resume":
            return self._continue(message)
        if kind in ("plan", "plan_execute"):
            state = self.planner.prepare(message)
            display = self._show(state)
            if kind == "plan":
                return display + "\nDiga 'execute o plano' para iniciar."
            return self._show(
                self._execute()
            )
        return None
