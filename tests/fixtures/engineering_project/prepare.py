from pathlib import Path
import subprocess
import sys
import venv

root = Path(__file__).resolve().parent
target = root / '.venv'
if target.exists():
    raise SystemExit('Refusing duplicate environment installation')
venv.EnvBuilder(with_pip=True, symlinks=False).create(target)
subprocess.run([str(target / 'bin/python'), '-m', 'pip', '--isolated', 'install',
    '--no-index', '--no-deps', '--no-compile', '--disable-pip-version-check',
    '--require-hashes', '--find-links', sys.argv[1], '-r', str(root / 'requirements.txt')], check=True)
(root / 'install-count.txt').write_text('1\n')
