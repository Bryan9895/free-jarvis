"""Explicit observed postconditions; no commands are repeated by verification."""
import hashlib
import re

from .filesystem_tools import ToolError, MAX_FILE_BYTES


def validate(toolkit, checks):
    if not isinstance(checks, dict) or checks.keys() - {'project', 'revision', 'distributions', 'files', 'stdout_sha256'}:
        raise ToolError('Pós-condições inválidas')
    if not checks or not (checks.get('revision') or checks.get('distributions') or checks.get('files') or checks.get('stdout_sha256')):
        raise ToolError('Informe pelo menos uma pós-condição concreta')
    if 'revision' in checks and (not isinstance(checks['revision'], str) or not re.fullmatch(r'[0-9a-f]{40,64}', checks['revision'])):
        raise ToolError('Revisão esperada inválida')
    if 'project' in checks: toolkit.path(checks['project'])
    if (checks.get('revision') or checks.get('distributions')) and not checks.get('project'):
        raise ToolError('Revisão/distribuições exigem projeto explícito')
    if 'distributions' in checks and (not isinstance(checks['distributions'], list) or not 1 <= len(checks['distributions']) <= 100
            or not all(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', name) for name in checks['distributions'])):
        raise ToolError('Distribuições esperadas inválidas')
    if 'stdout_sha256' in checks and (not isinstance(checks['stdout_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', checks['stdout_sha256'])):
        raise ToolError('Hash de saída inválido')
    if 'files' in checks:
        if not isinstance(checks['files'], list) or not 1 <= len(checks['files']) <= 30:
            raise ToolError('Lista de arquivos inválida')
        for item in checks['files']:
            if not isinstance(item, dict) or set(item) != {'path', 'sha256'} or not isinstance(item['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
                raise ToolError('Arquivo/hash esperado inválido')
            toolkit.path(item['path'])


def observe(toolkit, checks, *, stdout=None):
    validate(toolkit, checks)
    evidence, passed = {}, True
    if checks.get('project'):
        checkpoint = toolkit.project_checkpoint(checks['project'], checks.get('revision', ''), checks.get('distributions'))
        evidence['project'] = checkpoint
        passed &= bool(checkpoint.get('effect_verified'))
    if checks.get('files'):
        evidence['files'] = []
        for item in checks['files']:
            path = toolkit.path(item['path'])
            matched = path.is_file() and path.stat().st_size <= MAX_FILE_BYTES and hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
            evidence['files'].append({'path': str(path), 'sha256': item['sha256'], 'matched': bool(matched)})
            passed &= matched
    if checks.get('stdout_sha256'):
        matched = stdout is not None and hashlib.sha256(stdout.encode()).hexdigest() == checks['stdout_sha256']
        evidence['stdout_matched'] = matched
        passed &= matched
    return bool(passed), evidence
