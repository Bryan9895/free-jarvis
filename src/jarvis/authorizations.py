"""Concessões explícitas, versionadas e atômicas; sem credenciais."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from threading import RLock


CATEGORIES = {
    'files': 'Arquivos nas pastas escolhidas',
    'applications': 'Aplicativos e janelas',
    'terminal': 'Terminal e scripts nas pastas autorizadas',
    'external': 'Rede e comunicação externa',
    'administration': 'Administração: pacotes e serviços do sistema',
    'secrets': 'Dados sensíveis e execução sem isolamento da conta',
    'sensitive': 'Ações com risco de perda de dados',
}


@dataclass(frozen=True)
class Grants:
    categories: frozenset = frozenset()
    roots: tuple = ()
    version: int = 1

    def validate(self):
        if type(self.version) is not int or self.version != 1 or self.categories - CATEGORIES.keys():
            raise ValueError('Concessões inválidas')
        for value in self.roots:
            path = Path(value).expanduser()
            if not path.is_absolute() or path.resolve() == Path('/') or not path.is_dir():
                raise ValueError('Escolha uma pasta existente; a raiz do sistema não é permitida')
        return self


class AuthorizationStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('JARVIS_AUTHORIZATIONS',
            '~/.config/jarvis-fcc/authorizations.json')).expanduser()
        self.lock = RLock()
        self.error = None
        self.current = self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict) or set(data) != {'version', 'categories', 'roots'}:
                raise ValueError('Esquema de concessões inválido')
            if not isinstance(data['categories'], list) or not isinstance(data['roots'], list):
                raise ValueError('Listas de concessões inválidas')
            if not all(isinstance(x, str) for x in data['categories'] + data['roots']):
                raise ValueError('Concessão inválida')
            return Grants(frozenset(data['categories']), tuple(data['roots']), data['version']).validate()
        except FileNotFoundError:
            return Grants()
        except (OSError, ValueError, TypeError) as exc:
            self.error = str(exc)
            return Grants()

    def snapshot(self):
        with self.lock:
            return self.current

    def save(self, grants):
        grants.validate()
        # Canonicalizar antes de persistir; um symlink não é uma nova raiz.
        grants = Grants(grants.categories, tuple(str(Path(p).expanduser().resolve()) for p in grants.roots))
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, filename = tempfile.mkstemp(prefix='.authorizations-', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'w') as output:
                    json.dump({'version': 1, 'categories': sorted(grants.categories),
                               'roots': list(grants.roots)}, output, ensure_ascii=False, indent=2)
                    output.write('\n')
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(filename, self.path)
                self.current, self.error = grants, None
            finally:
                Path(filename).unlink(missing_ok=True)

    def permits(self, category):
        return category in self.snapshot().categories


def protected_paths():
    home = Path.home()
    values = ('.ssh', '.gnupg', '.aws', '.codex', '.mozilla', '.config/google-chrome',
              '.config/chromium', '.local/share/keyrings', '.config/jarvis-fcc')
    paths = [home / value for value in values]
    for variable in ('JARVIS_AUTHORIZATIONS', 'JARVIS_PREFERENCES'):
        if os.getenv(variable):
            paths.append(Path(os.environ[variable]).expanduser().resolve())
    return paths


def is_sensitive_path(path):
    path = Path(path).resolve()
    return (any(path == p or path.is_relative_to(p) for p in protected_paths())
            or any(part == '.env' or part.startswith('.env.') or part.endswith(('.pem', '.key'))
                   for part in path.parts))
