#!/usr/bin/env bash
# Inicia a GUI com a chave de ElevenLabs somente na memória da sessão.
# NUNCA grava o segredo no Git, no histórico ou em arquivos de projeto.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/adam ]; then
  echo "ADAM não instalado. Execute: bash tools/install_ubuntu.sh" >&2
  exit 1
fi
if [ -z "${ELEVENLABS_API_KEY:-}" ] && [ -t 0 ]; then
  read -r -s -p "Chave ElevenLabs (Enter = usar texto sem voz): " ELEVENLABS_API_KEY || :
  echo
  export ELEVENLABS_API_KEY
fi
exec .venv/bin/adam --gui "$@"
