"""Verificação independente dos efeitos do executor no sistema de arquivos.

Somente caminhos de resultados reais, dentro de raízes autorizadas. Dados do
modelo e do histórico não são interpretados como comandos. Nunca executa shell.
"""
import hashlib
from pathlib import Path

_FILE_STATES = {"write_file", "make_directory", "create_python_project",
                "move_path", "delete_path"}
_LAUNCHERS = {"open_file", "open_project", "launch_installed_app",
              "desktop_open_app"}


def verify_step(toolkit, outcomes):
    """Retorna (estado, evidências), sem afirmar que uma GUI apareceu."""
    evidence = []
    saw_mutation = False
    saw_launch = False
    for action in outcomes:
        if not isinstance(action, dict):
            continue
        name = action.get("name")
        if name not in _FILE_STATES | _LAUNCHERS:
            continue
        outcome = action.get("outcome")
        if not isinstance(outcome, dict) or outcome.get("error"):
            continue
        result = outcome.get("result")
        if not isinstance(result, dict):
            continue
        status = result.get("status")
        if name in _LAUNCHERS:
            if status == "launched_unverified":
                saw_launch = True
                observation = action.get("window_observation")
                window_state = (observation or {}).get("status") if isinstance(observation, dict) else None
                details = {
                    "appeared_after_request": "Janela apareceu após o pedido; causalidade não comprovada",
                    "already_observed": "Janela já existia antes da solicitação",
                    "observed_unknown_origin": "Janela observada; estado anterior indisponível",
                    "not_observed": "Janela não observada; não significa que abertura falhou",
                    "unavailable": "Inventário de janelas indisponível",
                }
                evidence.append({"tool": name, "status": "unverified",
                                 "detail": details.get(window_state, "Lançador iniciado; janela não confirmada"),
                                 "window_status": window_state or "unknown"})
            continue
        if status not in ("created", "written", "moved", "trashed"):
            continue
        saw_mutation = True
        raw_path = result.get("trash_path") if name == "delete_path" else result.get("path")
        if not isinstance(raw_path, str):
            evidence.append({"tool": name, "status": "unverified",
                             "detail": "Sem caminho para verificar"})
            continue
        try:
            path = toolkit.path(raw_path)
            if name == "make_directory" or name == "create_python_project":
                valid = path.is_dir()
                if valid and name == "create_python_project":
                    valid = all((path / child).is_file()
                                for child in ("main.py", "README.md", ".gitignore"))
            elif name == "delete_path":
                valid = path.exists()
                original = result.get("previous_path")
                if valid and isinstance(original, str):
                    valid = not toolkit.path(original).exists()
            else:
                valid = path.is_file() if name == "write_file" else path.exists()
                if valid and name == "write_file":
                    expected = action.get("expected_sha256")
                    if not isinstance(expected, str):
                        evidence.append({"tool": name, "status": "unverified",
                                         "detail": "Sem hash esperado para comparar conteúdo"})
                        continue
                    valid = (hashlib.sha256(path.read_bytes()).hexdigest() == expected)
            evidence.append({"tool": name, "status": "verified" if valid else "failed",
                             "detail": "Estado do sistema de arquivos conferido" if valid
                             else "Resultado ausente ou diferente do esperado"})
        except (OSError, ValueError, UnicodeError):
            evidence.append({"tool": name, "status": "failed",
                             "detail": "Falha ao conferir caminho autorizado"})
    if any(item["status"] == "failed" for item in evidence):
        return "failed", evidence
    if saw_launch:
        return "unverified", evidence
    if saw_mutation and evidence and all(x["status"] == "verified" for x in evidence):
        return "verified", evidence
    return "unverified", evidence
