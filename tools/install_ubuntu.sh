#!/usr/bin/env bash
# Instalador nativo Ubuntu. Nunca usa sudo pip nem --break-system-packages.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo "Instale Python 3.10+."; exit 1; }
if ! python3 -c 'import sys; assert sys.version_info >= (3,10)'; then
  echo "ADAM requer Python 3.10+."; exit 1
fi
if ! python3 -c 'import venv, tkinter' >/dev/null 2>&1; then
  echo "Dependências do sistema ausentes. Execute:"
  echo "  sudo apt update && sudo apt install python3-venv python3-tk python3-full"
  exit 1
fi
if ! python3 -c 'import ctypes.util; assert ctypes.util.find_library("portaudio")' >/dev/null 2>&1; then
  echo "Biblioteca de áudio ausente. Execute: sudo apt install libportaudio2 libsndfile1"
  exit 1
fi
if ! command -v aplay >/dev/null && ! command -v paplay >/dev/null; then
  echo "Instale um reprodutor: sudo apt install pulseaudio-utils alsa-utils"
fi
if [ ! -f .venv/bin/python ]; then
  echo "Criando ambiente virtual isolado (.venv)..."
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -e '.[voice,desktop]'
echo
echo "ADAM instalado no ambiente privado. Para iniciar:"
echo "  cd $(pwd)"
echo "  source .venv/bin/activate"
echo "  export FCC_URL=http://127.0.0.1:8082"
echo "  export ELEVENLABS_API_KEY='sua-chave'  # apenas se quiser ouvir a voz"
echo "  adam --gui"
echo "Para testar só a interface e mensagens escritas: adam --gui --text-only"
