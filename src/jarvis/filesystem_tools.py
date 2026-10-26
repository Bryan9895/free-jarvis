"""Operações locais de arquivos e comandos de inspeção."""
import os
import hashlib
import difflib
import shlex
import subprocess
import tempfile
import uuid
import shutil
from pathlib import Path

MAX_FILE_BYTES = 100_000


class ToolError(ValueError):
    """Entrada de ferramenta inválida ou fora da política local."""


class FilesystemTools:
    def path(self, requested: str) -> Path:
        if not isinstance(requested, str):
            raise ToolError("Caminho inválido")
        p = (self.workspace / requested).resolve()
        if not any(p.is_relative_to(root) for root in self.allowed_roots):
            raise ToolError("Acesso fora dos diretórios autorizados bloqueado")
        from .authorizations import is_sensitive_path
        if is_sensitive_path(p):
            authorize = getattr(self.approve, 'authorize', None)
            if authorize is None or not authorize('secrets', 'ACESSAR DADO SENSÍVEL: ' + str(p)):
                raise ToolError('Acesso a dados sensíveis não autorizado')
        return p

    def _safe_mutation_path(self, requested):
        if not isinstance(requested, str):
            raise ToolError("Caminho inválido")
        raw = Path(requested).expanduser()
        if not raw.is_absolute():
            raw = self.workspace / raw
        raw = Path(os.path.abspath(raw))
        for root in self.allowed_roots:
            if raw.is_relative_to(root):
                candidate = raw
                while candidate != root:
                    if candidate.is_symlink():
                        raise ToolError("Links simbólicos não são aceitos em alterações")
                    candidate = candidate.parent
                return self.path(requested)
        raise ToolError("Acesso fora dos diretórios autorizados bloqueado")

    def _is_root(self, path):
        return path in self.allowed_roots

    def list_files(self, path="."):
        p = self.path(path)
        if not p.is_dir():
            raise ToolError("Diretório inexistente")
        return [{"name": x.name, "directory": x.is_dir()} for x in sorted(p.iterdir())[:120]]

    def read_file(self, path):
        p = self.path(path)
        if not p.is_file():
            raise ToolError("Arquivo inexistente")
        if p.stat().st_size > MAX_FILE_BYTES:
            raise ToolError("Arquivo muito grande (limite 100 KB)")
        return p.read_text(encoding="utf-8")

    def write_file(self, path, content, expected_sha256=None):
        p = self._safe_mutation_path(path)
        if not isinstance(content, str) or len(content.encode()) > MAX_FILE_BYTES:
            raise ToolError("Conteúdo inválido ou arquivo muito grande")
        if p.exists() and not p.is_file():
            raise ToolError("O destino não é um arquivo regular")
        if p.exists() and p.stat().st_size > MAX_FILE_BYTES:
            raise ToolError("Arquivo existente muito grande para edição segura")
        before = p.read_bytes() if p.exists() else None
        before_hash = hashlib.sha256(before).hexdigest() if before is not None else None
        if expected_sha256 is not None and expected_sha256 != before_hash:
            raise ToolError("Arquivo mudou desde a leitura; conteúdo esperado não confere")
        try:
            previous = before.decode("utf-8") if before is not None else ""
        except UnicodeDecodeError as exc:
            raise ToolError("Arquivo existente não é texto UTF-8") from exc
        diff = "".join(difflib.unified_diff(
            previous.splitlines(keepends=True), content.splitlines(keepends=True),
            fromfile=str(p) if before is not None else "/dev/null", tofile=str(p),
        ))
        summary = diff[:4000] + ("\n[diff truncado]" if len(diff) > 4000 else "")
        if not self.approve(f"ESCREVER {p} ({len(content)} caracteres)\n{summary}"):
            return {"status": "rejected"}
        p = self._safe_mutation_path(path)
        if p.exists() and not p.is_file():
            raise ToolError("O destino mudou desde a autorização")
        current = p.read_bytes() if p.exists() else None
        if current != before:
            raise ToolError("O arquivo mudou durante a autorização; escrita cancelada")
        p.parent.mkdir(parents=True, exist_ok=True)
        p = self._safe_mutation_path(path)
        if (p.read_bytes() if p.exists() else None) != before:
            raise ToolError("O arquivo mudou antes da escrita; operação cancelada")
        fd, temporary = tempfile.mkstemp(prefix=".jarvis-write-", dir=p.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                if before is not None:
                    os.fchmod(output.fileno(), p.stat().st_mode & 0o777)
                output.write(content.encode("utf-8"))
                output.flush()
                os.fsync(output.fileno())
            p = self._safe_mutation_path(path)
            if (p.read_bytes() if p.exists() else None) != before:
                raise ToolError("O arquivo mudou antes da substituição; operação cancelada")
            os.replace(temporary, p)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return {"status": "written", "path": str(p),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}

    def make_directory(self, path):
        destination = self._safe_mutation_path(path)
        if self._is_root(destination):
            raise ToolError("Escolha uma subpasta do workspace")
        if destination.exists():
            raise ToolError("O caminho já existe")
        if not self.approve(f"CRIAR PASTA {destination}"):
            return {"status": "rejected"}
        # Revalidar após a confirmação.
        destination = self._safe_mutation_path(path)
        destination.mkdir(parents=True, exist_ok=False)
        return {"status": "created", "path": str(destination)}

    def create_python_project(self, path):
        """Cria estrutura Python mínima sem instalar pacotes nem executar código."""
        folder = self._safe_mutation_path(path)
        if self._is_root(folder) or folder.exists():
            raise ToolError("Escolha uma nova subpasta de projeto")
        if not folder.parent.is_dir():
            raise ToolError("A pasta pai precisa existir")
        if not self.approve(f"CRIAR PROJETO PYTHON {folder} (main.py, README.md, .gitignore)?"):
            return {"status": "rejected"}
        folder = self._safe_mutation_path(path)
        if folder.exists() or not folder.parent.is_dir():
            raise ToolError("O destino mudou desde a autorização")
        folder.mkdir(exist_ok=False)
        (folder / "main.py").write_text(
            'def main():\n    print("Olá, mundo!")\n\n\nif __name__ == "__main__":\n    main()\n',
            encoding="utf-8")
        (folder / "README.md").write_text(
            f"# {folder.name}\n\nProjeto Python criado pela JARVIS.\n",
            encoding="utf-8")
        (folder / ".gitignore").write_text(
            "__pycache__/\n*.py[cod]\n.venv/\n",
            encoding="utf-8")
        return {"status": "created", "path": str(folder),
                "files": ["main.py", "README.md", ".gitignore"]}

    def move_path(self, source, destination):
        src, dst = self._safe_mutation_path(source), self._safe_mutation_path(destination)
        if self._is_root(src) or self._is_root(dst) or src == self.workspace / ".jarvis-trash":
            raise ToolError("Não é permitido mover a raiz do workspace nem a lixeira")
        if src == dst or not src.exists() or dst.exists():
            raise ToolError("Origem ausente, destino existente ou caminhos idênticos")
        if src.is_symlink() or dst.is_symlink():
            raise ToolError("Links simbólicos não são aceitos nesta operação")
        if src.is_dir() and dst.is_relative_to(src):
            raise ToolError("Não é possível mover uma pasta para dentro dela mesma")
        if not dst.parent.is_dir():
            raise ToolError("A pasta de destino precisa existir")
        if not self.approve(f"MOVER {src} PARA {dst}"):
            return {"status": "rejected"}
        src, dst = self._safe_mutation_path(source), self._safe_mutation_path(destination)
        if not src.exists() or dst.exists():
            raise ToolError("Os caminhos mudaram; operação cancelada")
        moved = shutil.move(str(src), str(dst))
        return {"status": "moved", "path": moved}

    def delete_path(self, path):
        """Move para a lixeira interna do workspace, sem excluir definitivamente."""
        target = self._safe_mutation_path(path)
        trash = self.workspace / ".jarvis-trash"
        if self._is_root(target) or target == trash or target.is_relative_to(trash):
            raise ToolError("Não é permitido remover a raiz ou a lixeira")
        if target.is_symlink() or not target.exists():
            raise ToolError("Caminho inexistente ou link simbólico não permitido")
        if not self.approve(f"MOVER PARA LIXEIRA INTERNA {target}"):
            return {"status": "rejected"}
        target = self._safe_mutation_path(path)
        if not target.exists() or target.is_symlink():
            raise ToolError("Caminho alterado desde a autorização")
        trash.mkdir(exist_ok=True)
        destination = trash / (uuid.uuid4().hex + "-" + target.name)
        shutil.move(str(target), str(destination))
        return {"status": "trashed", "previous_path": str(target), "trash_path": str(destination)}

    def run_command(self, command, cwd="."):
        """Executa apenas comandos de inspeção exatos, sem shell."""
        try:
            args = shlex.split(command)
        except (TypeError, ValueError) as exc:
            raise ToolError("Comando inválido") from exc
        allowed = (
            ["pwd"], ["ls"], ["ls", "-la"], ["ls", "-l"], ["ls", "-a"],
            ["git", "status"], ["git", "status", "--short"],
            ["git", "diff"], ["git", "branch"], ["git", "remote"],
            ["git", "log", "-1"], ["git", "log", "--oneline"],
            ["gh", "auth", "status"], ["gh", "repo", "list"],
        )
        if args not in allowed:
            raise ToolError("Comando ou argumentos não permitidos nesta versão")
        run = subprocess.run(args, cwd=self.path(cwd), capture_output=True, text=True,
                             timeout=15, check=False,
                             env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_PAGER": "cat", "PAGER": "cat"})
        return {"exit_code": run.returncode, "stdout": run.stdout[:10000], "stderr": run.stderr[:1500]}

