"""Equipe de engenharia verificável; não depende de modelos Anthropic.

FCC-CLAUDE (supervisor/dev) e Codex crítico são processos separados.
Sem resposta estruturada do crítico e testes reais, não gera commit/push.
Este utilitário NÃO é o motor de conversa do ADAM.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


class TeamError(RuntimeError):
    pass


def review_report(raw):
    """Revisão Codex estritamente estruturada. Incerteza sempre bloqueia."""
    try:
        value = json.loads(raw.strip())
    except (TypeError, ValueError) as exc:
        raise TeamError("Revisão não retornou JSON válido; bloqueado.") from exc
    if (not isinstance(value, dict) or set(value) != {"verdict", "findings"}
            or value["verdict"] not in ("approve", "changes_requested")
            or not isinstance(value["findings"], list)
            or any(not isinstance(finding, str) or len(finding) > 1000
                   for finding in value["findings"]) or len(value["findings"]) > 20):
        raise TeamError("Revisão Codex com esquema inesperado; bloqueado.")
    if value["verdict"] == "approve" and value["findings"]:
        raise TeamError("Revisão contraditória; bloqueado.")
    if value["verdict"] == "changes_requested" and not value["findings"]:
        raise TeamError("Revisão não justificou a correção; bloqueado.")
    return value


class CommandAgent:
    """Executa uma ferramenta configurada pelo usuário; nunca usa shell=True."""
    def __init__(self, command, workdir, *, timeout=360):
        self.command = shlex.split(command)
        if not self.command:
            raise ValueError("Comando de agente vazio")
        self.workdir = Path(workdir)
        self.timeout = timeout

    def run(self, prompt):
        result = subprocess.run(self.command, input=prompt, cwd=self.workdir,
                                capture_output=True, text=True, timeout=self.timeout)
        if result.returncode:
            raise TeamError("Agente falhou (sem executar commit): "
                            + (result.stderr or result.stdout)[-600:])
        return result.stdout[-65000:]


class EngineeringTeam:
    def __init__(self, supervisor, developer, reviewer, run_tests, *, max_rounds=3):
        if not 1 <= max_rounds <= 5:
            raise ValueError("Máximo de 1 a 5 ciclos")
        self.supervisor, self.developer, self.reviewer = supervisor, developer, reviewer
        self.run_tests = run_tests
        self.max_rounds = max_rounds
        self.log = []

    def run(self, task):
        if not isinstance(task, str) or not task.strip():
            raise ValueError("Tarefa vazia")
        plan = self.supervisor.run("Planeje a implementação de ADAM sem publicar código. "
                                   "Respeite AGENTS.md, FCC e interface Tkinter. Tarefa:\n" + task)
        self.log.append("supervisor_ok")
        feedback = ""
        for index in range(self.max_rounds):
            self.developer.run(
                "Implemente a tarefa no worktree atual. NÃO faça commits nem push. "
                "Não contorne permissões do Claude Code. Plano do supervisor:\n" + plan
                + ("\nFeedback obrigatório:\n" + feedback if feedback else ""))
            self.log.append("developer_ran")
            raw = self.reviewer.run(
                "Revise criticamente as alterações REAIS no git diff; não aceite "
                "respostas sem testes. Retorne SOMENTE JSON "
                '{"verdict":"approve|changes_requested","findings":["..."]}. '
                "Para aprovação, findings deve ser []. Verifique segurança, "
                "funcionalidade, regressões e conformidade com AGENTS.md.")
            review = review_report(raw)
            self.log.append("codex_" + review["verdict"])
            if review["verdict"] != "approve":
                feedback = "\n".join(review["findings"])
                continue
            success, detail = self.run_tests()
            self.log.append("tests_passed" if success else "tests_failed")
            if success:
                return {"approved": True, "rounds": index + 1, "log": list(self.log)}
            feedback = "Testes falharam; corrija antes de nova revisão:\n" + str(detail)[-2000:]
        return {"approved": False, "rounds": self.max_rounds, "log": list(self.log)}


def tests_command(workdir, args):
    command = shlex.split(args)
    if not command:
        raise ValueError("Comando de teste vazio")
    result = subprocess.run(command, cwd=workdir, capture_output=True, text=True,
                            timeout=600)
    return result.returncode == 0, (result.stdout + result.stderr)[-2500:]


def git_verify_worktree(workdir):
    def git(*args):
        result = subprocess.run(["git", *args], cwd=workdir, text=True,
                                capture_output=True, timeout=30)
        if result.returncode:
            raise TeamError("Comando Git falhou: " + " ".join(args))
        return result.stdout.strip()
    branch = git("branch", "--show-current")
    if not branch or branch in ("main", "master"):
        raise TeamError("Abra uma branch/worktree de desenvolvimento antes de rodar a equipe.")
    if git("status", "--porcelain"):
        raise TeamError("Worktree sujo. Preserve ou registre as alterações antes de iniciar.")
    return branch


def publish_reviewed(workdir, *, push=False):
    def git(*args):
        result = subprocess.run(["git", *args], cwd=workdir, text=True,
                                capture_output=True, timeout=120)
        if result.returncode:
            raise TeamError("Git falhou (" + args[0] + "): " + result.stderr[-400:])
        return result.stdout.strip()
    changed = set(filter(None, git("status", "--porcelain").splitlines()))
    if not changed:
        raise TeamError("Nenhum arquivo alterado após a revisão.")
    forbidden = re.compile(r"(^|/)(\.env($|\.)|\.venv/|id_rsa|.*\.(pem|key|p12)$)", re.I)
    for entry in changed:
        name = entry[3:].strip().split(" -> ")[-1]
        if forbidden.search(name):
            raise TeamError("Arquivo potencialmente sensível impede commit automático: " + name)
    git("add", "--all")
    git("commit", "-m", "feat(adam): alterações revisadas pelo fluxo supervisor-dev-codex")
    if push:
        branch = git("branch", "--show-current")
        git("push", "--set-upstream", "origin", branch)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="ADAM engineering team · fluxo verificável")
    parser.add_argument("--task-file", required=True, type=Path)
    parser.add_argument("--supervisor-cmd", required=True)
    parser.add_argument("--developer-cmd", required=True)
    parser.add_argument("--reviewer-cmd", required=True)
    parser.add_argument("--tests", default="python -m unittest discover -s tests -q")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--push", action="store_true",
                        help="Publicar branch no GitHub somente se revisão e testes passarem")
    args = parser.parse_args(argv)
    cwd = Path.cwd()
    git_verify_worktree(cwd)
    if not args.task_file.is_file() or args.task_file.stat().st_size > 15000:
        parser.error("Tarefa ausente ou maior que 15 KB")
    team = EngineeringTeam(
        CommandAgent(args.supervisor_cmd, cwd),
        CommandAgent(args.developer_cmd, cwd, timeout=1500),
        CommandAgent(args.reviewer_cmd, cwd, timeout=600),
        lambda: tests_command(cwd, args.tests),
        max_rounds=args.max_rounds,
    )
    result = team.run(args.task_file.read_text(encoding="utf-8"))
    print(json.dumps(result, ensure_ascii=False))
    if not result["approved"]:
        return 2
    publish_reviewed(cwd, push=args.push)
    return 0


if __name__ == "__main__":
    sys.exit(main())
