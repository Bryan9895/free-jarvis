"""Explicit Linux project services, durable identity and conservative restart."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
from time import monotonic
from threading import Event
from threading import Thread
from contextlib import closing
from urllib.request import ProxyHandler, build_opener
from urllib.parse import urlsplit

from .cancellation import CancellationToken
from .local_setup import _installation_lock


def identity(pid):
    try:
        stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z' or Path(f'/proc/{pid}').stat().st_uid != os.getuid():
            return None
        return {'pid': pid, 'starttime': stat[19],
                'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, IndexError, ValueError):
        return None


def group_alive(group):
    try:
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit(): continue
            try:
                fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                if fields[0] != 'Z' and int(fields[2]) == group:
                    return True
            except FileNotFoundError:
                continue
        return False
    except (OSError, ValueError, IndexError):
        return True  # An unreadable inventory cannot prove the group stopped.


def health_url(value):
    from .local_provider import local_host
    parsed = urlsplit(value)
    origin = local_host(f'{parsed.scheme}://{parsed.netloc}')
    if parsed.query or parsed.fragment or not parsed.path.startswith('/'):
        raise ValueError('Health exige URL HTTP de loopback, caminho e sem query/fragmento')
    return origin + parsed.path


def healthy(url):
    try:
        opener = build_opener(ProxyHandler({}))
        # A redirect must not turn a loopback health probe into external access.
        from urllib.request import HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        opener.add_handler(NoRedirect())
        with opener.open(url, timeout=.3) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def owns_health_port(pid, url):
    """Do not mistake another process's HTTP 200 for this service's readiness."""
    port = urlsplit(url).port
    try:
        inodes = {os.readlink(fd)[8:-1] for fd in Path(f'/proc/{pid}/fd').iterdir()
                  if os.readlink(fd).startswith('socket:[')}
        for family in ('tcp', 'tcp6'):
            for line in Path(f'/proc/{pid}/net/{family}').read_text().splitlines()[1:]:
                fields = line.split()
                if fields[3] == '0A' and int(fields[1].split(':')[1], 16) == port and fields[9] in inodes:
                    return True
    except (OSError, ValueError, IndexError):
        pass
    return False


class ProjectServices:
    def __init__(self, database):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.children = {}

    def operate(self, action, name, cwd, *, argv=None, health='', token=None):
        if os.name != 'posix' or not Path('/proc/self/stat').exists():
            raise ValueError('Serviços de projeto ainda exigem Linux')
        if action not in ('start', 'status', 'stop') or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}', name):
            raise ValueError('Ação/nome do serviço inválido')
        token = token or CancellationToken()
        root = self.database.parent / '.project-service-lock'
        root.mkdir(mode=0o700, exist_ok=True)
        with _installation_lock(root, token), closing(sqlite3.connect(self.database)) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS project_services '
                         '(project TEXT, name TEXT, payload TEXT NOT NULL, PRIMARY KEY(project,name))')
            project = str(Path(cwd).resolve())
            row = conn.execute('SELECT payload FROM project_services WHERE project=? AND name=?', (project, name)).fetchone()
            record = json.loads(row[0]) if row else None
            def save():
                conn.execute('INSERT OR REPLACE INTO project_services VALUES (?,?,?)', (project, name, json.dumps(record)))
                conn.commit()
            def observe():
                current = identity(record['identity']['pid']) if record and record.get('identity') else None
                same = current is not None and current == record.get('identity')
                if not same:
                    return {'status': 'unverified' if record and record['state'] != 'stopped' else 'not_running',
                            'reason': 'identity_not_observed', 'effect_verified': False, 'name': name}
                ready = owns_health_port(current['pid'], record['health']) and healthy(record['health'])
                return {'status': 'verified' if ready else 'unverified', 'effect_verified': ready,
                        'running': True, 'health_ok': ready, 'identity': current, 'name': name}
            if action == 'status':
                return observe()
            if action == 'stop':
                observed = observe()
                if not observed.get('running'):
                    previous = record.get('identity') if record else None
                    if previous and not group_alive(previous['pid']):
                        record['state'] = 'stopped'
                        save()
                        return {'status': 'verified', 'effect_verified': True, 'stopped': True, 'name': name}
                    return observed
                pid = record['identity']['pid']
                token.check()
                if os.getpgid(pid) != pid or identity(pid) != record['identity']:
                    return {'status': 'unverified', 'reason': 'identity_changed', 'effect_verified': False}
                os.killpg(pid, signal.SIGTERM)
                deadline = monotonic() + 2
                while identity(pid) == record['identity'] and monotonic() < deadline:
                    Event().wait(.02)
                if identity(pid) == record['identity']:
                    if os.getpgid(pid) == pid:
                        os.killpg(pid, signal.SIGKILL)
                    Event().wait(.05)
                stopped = identity(pid) != record['identity'] and not group_alive(pid)
                child = self.children.pop(pid, None)
                if child: child.wait(timeout=1)
                if stopped:
                    record['state'] = 'stopped'
                    save()
                return {'status': 'verified' if stopped else 'unverified', 'effect_verified': stopped,
                        'stopped': stopped, 'name': name}
            url = health_url(health)
            if (not isinstance(argv, list) or not 1 <= len(argv) <= 128 or not all(
                    isinstance(item, str) and 0 < len(item) <= 8192 and '\x00' not in item for item in argv)):
                raise ValueError('argv inválido')
            digest = hashlib.sha256(json.dumps([argv, url]).encode()).hexdigest()
            if record and record['state'] != 'stopped':
                observed = observe()
                if record.get('command_sha256') != digest:
                    return {'status': 'unverified', 'reason': 'configuration_changed_stop_first', 'effect_verified': False}
                return {**observed, 'reused': bool(observed.get('running')),
                        'restart': 'blocked_until_previous_effect_is_resolved'}
            records = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM project_services')]
            if sum(r['state'] != 'stopped' for r in records) >= 2:
                raise ValueError('Limite de dois serviços; encerre/resolva os anteriores')
            token.check()
            record = {'state': 'starting', 'command_sha256': digest, 'health': url, 'identity': None}
            save()  # Durable intent before any effect; crash cannot cause an automatic retry.
            env = {key: os.environ[key] for key in ('LANG', 'SYSTEMROOT') if key in os.environ}
            env.update(PATH='/usr/local/bin:/usr/bin:/bin', HOME=str(Path.home()), LC_ALL='C.UTF-8')
            try:
                child = subprocess.Popen(argv, cwd=project, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, start_new_session=True)
            except OSError:
                record['state'] = 'stopped'
                save()
                raise
            self.children[child.pid] = child
            Thread(target=child.wait, daemon=True, name='jarvis-project-reaper').start()
            record['identity'] = identity(child.pid)
            record['state'] = 'started'
            save()
            try:
                deadline = monotonic() + 5
                while monotonic() < deadline:
                    token.check()
                    observed = observe()
                    if observed['effect_verified'] or not observed.get('running'):
                        return {**observed, 'reused': False}
                    Event().wait(.05)
                return {**observe(), 'reused': False}
            except BaseException:
                if identity(child.pid) == record['identity'] and os.getpgid(child.pid) == child.pid:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=.5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=1)
                    record['state'] = 'stopped'
                    save()
                raise


class ProjectServiceTools:
    def project_service(self, action, name, cwd='.', argv=None, health=''):
        directory = self.path(cwd)
        authorize = getattr(self.approve, 'authorize', None)
        if action != 'status':
            if authorize is None or not authorize('terminal', f'SERVIÇO DE PROJETO: {action} {name} em {directory}: ' + repr(argv)[:1500]):
                return {'status': 'rejected'}
            if action == 'start' and not self.approve.granted('secrets') and not authorize('secrets',
                    'EXECUTAR SERVIÇO COM ACESSO AOS DADOS DA CONTA: ' + repr(argv)[:1500]):
                return {'status': 'rejected'}
        self._check_execution()
        if not hasattr(self, '_project_services'):
            self._project_services = ProjectServices(self.layout_db or self.workspace / '.jarvis-services.sqlite3')
        return self._project_services.operate(action, name, directory, argv=argv, health=health,
                                             token=self._execution_token)
