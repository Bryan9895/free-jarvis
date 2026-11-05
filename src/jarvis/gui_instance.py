"""Per-user, per-graphical-session GUI lease and show-only local IPC."""
import hashlib
import os
from pathlib import Path
import socket
import stat
import struct
from threading import Event, Thread


class GuiInstance:
    def __init__(self, directory=None):
        session = '|'.join(os.getenv(key, '') for key in ('XDG_SESSION_ID', 'WAYLAND_DISPLAY', 'DISPLAY'))
        suffix = hashlib.sha256(session.encode()).hexdigest()[:16]
        base = Path(directory) if directory else Path(os.getenv('XDG_RUNTIME_DIR') or Path.home() / '.cache') / 'jarvis-fcc'
        base.mkdir(parents=True, mode=0o700, exist_ok=True)
        info = base.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError('Diretório IPC precisa pertencer ao usuário e ter modo 0700')
        self.path = base / (suffix + '.sock')
        self.lock_path = base / (suffix + '.lock')
        self.lock = None
        self.socket = None
        self.thread = None
        self.stop = Event()

    @staticmethod
    def peer(connection):
        _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        return uid == os.getuid()

    def acquire_or_show(self):
        import fcntl
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(descriptor, 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(3)
                client.connect(str(self.path))
                if not self.peer(client):
                    raise PermissionError('Instância GUI de outro usuário')
                client.sendall(b'show\n')
                if client.recv(32) != b'queued\n':
                    raise RuntimeError('Instância GUI não confirmou o pedido de exibição')
            return False
        try:
            if self.path.is_symlink():
                raise PermissionError('Socket IPC não pode ser link simbólico')
            self.path.unlink(missing_ok=True)
            self.socket = socket.socket(socket.AF_UNIX)
            self.socket.bind(str(self.path))
            self.path.chmod(0o600)
            self.socket.listen(4)
            self.socket.settimeout(.2)
            return True
        except BaseException:
            self.close()
            raise

    def serve(self, show):
        def listen():
            while not self.stop.is_set():
                try:
                    connection, _ = self.socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return
                with connection:
                    connection.settimeout(.5)
                    try:
                        if self.peer(connection) and connection.recv(32) == b'show\n':
                            show()  # Queue only; Tk operations remain on its main thread.
                            connection.sendall(b'queued\n')
                    except OSError:
                        pass
        self.thread = Thread(target=listen, name='jarvis-gui-show', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.socket:
            self.socket.close()
        if self.thread:
            self.thread.join(timeout=1)
        if self.lock:
            self.path.unlink(missing_ok=True)
            self.lock.close()
            self.lock = None


def main():
    from .cli import main as cli
    cli(['--gui'])
