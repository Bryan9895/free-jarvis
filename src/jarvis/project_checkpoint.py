"""Observed project/revision/environment facts for durable engineering plans."""
import hashlib
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, urlunsplit


def inspect_project(directory):
    directory = Path(directory).resolve()
    def git(*args):
        try:
            result = subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-C', str(directory), *args],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                timeout=5, env={'PATH': '/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'},
                check=False)
            return result.stdout[:8192].decode(errors='replace').strip() if result.returncode == 0 else ''
        except (OSError, subprocess.TimeoutExpired):
            return ''
    revision = git('rev-parse', '--verify', 'HEAD')
    if not re.fullmatch(r'[a-f0-9]{40,64}', revision):
        return {'status': 'not_found', 'path': str(directory), 'effect_verified': False}
    url = git('config', '--get', 'remote.origin.url')
    if '://' in url:
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        if ':' in host: host = '[' + host + ']'
        url = urlunsplit((parsed.scheme, host + (f':{parsed.port}' if parsed.port else ''), parsed.path, '', ''))
    elif not re.fullmatch(r'git@[A-Za-z0-9.-]+:[A-Za-z0-9_./-]+', url):
        url = ''  # A local remote path or unknown URL can contain private data.
    environment = {'state': 'Falta', 'distributions': []}
    venv = directory / '.venv'
    if venv.resolve().is_relative_to(directory) and (venv / 'pyvenv.cfg').is_file():
        config = (venv / 'pyvenv.cfg').read_bytes()
        distributions = []
        for entry in sorted(venv.glob('lib/python*/site-packages/*.dist-info'))[:200]:
            if not entry.resolve().is_relative_to(venv.resolve()):
                continue
            metadata = entry / 'METADATA'
            if not metadata.is_file() or metadata.stat().st_size > 1024 * 1024:
                continue
            values = {}
            for line in metadata.read_text(errors='replace').splitlines():
                if line.startswith(('Name: ', 'Version: ')):
                    key, value = line.split(': ', 1)
                    values[key] = value[:128]
            if values.get('Name') and values.get('Version'):
                distributions.append({'name': values['Name'], 'version': values['Version'],
                    'metadata_sha256': hashlib.sha256(metadata.read_bytes()).hexdigest()})
        environment = {'state': 'OK' if (venv / 'bin/python').is_file() else 'Falta',
            'path': str(venv), 'config_sha256': hashlib.sha256(config).hexdigest(),
            'distributions': distributions}
    return {'status': 'verified', 'effect_verified': True, 'path': str(directory),
        'source_url': url, 'revision': revision, 'ref': git('symbolic-ref', '--short', '-q', 'HEAD'),
        'environment': environment}


class ProjectCheckpointTools:
    def project_checkpoint(self, path='.', expected_revision='', distributions=None):
        result = inspect_project(self.path(path))
        if result['status'] != 'verified':
            return result
        normalize = lambda name: re.sub(r'[-_.]+', '-', name).lower()
        present = {normalize(item['name']) for item in result['environment']['distributions']}
        missing = [item for item in distributions or [] if normalize(item) not in present]
        if expected_revision and result['revision'] != expected_revision or missing:
            result.update(status='failed', effect_verified=False, missing_distributions=missing)
        return result


def revalidate(toolkit, artifacts):
    try:
        return _revalidate(toolkit, artifacts)
    except (OSError, ValueError):
        return False


def _revalidate(toolkit, artifacts):
    """Check observations again before pending effects; never reinstall/relaunch here."""
    for artifact in artifacts:
        if artifact['tool'] == 'file':
            from .process_postconditions import observe
            if not observe(toolkit, {'files': [artifact['result']]})[0]:
                return False
        elif artifact['tool'] == 'execute_process':
            from .process_postconditions import observe
            checks = dict(artifact['result'].get('postconditions', {}))
            checks.pop('stdout_sha256', None)
            if not checks or not observe(toolkit, checks)[0]:
                return False
            previous = artifact['result'].get('evidence', {}).get('project')
            if previous and checks.get('distributions') and toolkit.project_checkpoint(checks['project']).get('environment') != previous.get('environment'):
                return False
        elif artifact['tool'] == 'project_checkpoint':
            before = artifact['result']
            now = toolkit.project_checkpoint(before['path'])
            if now.get('revision') != before.get('revision') or now.get('environment') != before.get('environment'):
                return False
        elif artifact['tool'] == 'project_service' and artifact['arguments'].get('action') == 'start':
            args = artifact['arguments']
            now = toolkit.project_service('status', args['name'], args.get('cwd', '.'))
            if not now.get('effect_verified') or now.get('identity') != artifact['result'].get('identity'):
                return False
    return True
