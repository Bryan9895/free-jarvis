# JARVIS FCC

Assistente pessoal em português para Ubuntu GNOME Wayland. A CLI e a GUI usam o mesmo núcleo para conversar com modelos do Free Claude Code (FCC), executar ferramentas locais autorizadas, organizar janelas e ambientes, trabalhar com arquivos e usar um navegador Chromium isolado. Esta branch prepara a v1.0; o pacote ainda declara **0.4.0** até passar todos os critérios de entrega.

## Instalação

Requer Python 3.10+ e um servidor FCC configurado separadamente. No diretório do repositório:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[desktop]"
jarvis-fcc --doctor
```

Para o navegador ou a voz, instale apenas o extra necessário:

```bash
python -m pip install -e ".[browser]"
python -m playwright install chromium
# Voz opcional: libportaudio2, alsa-utils e um modelo local Piper para síntese
python -m pip install -e ".[voice]"
```

A GUI usa Tkinter do Python do sistema (`python3-tk` no Ubuntu, se ausente). Chromium e áudio são carregados apenas quando usados. As extensões GNOME para inventário e controle de janelas são opcionais e devem ser instaladas pelo usuário; consulte [guia de uso](docs/GUIA_DE_USO.md).

## Configuração e início

```bash
export FCC_URL="http://127.0.0.1:8082"
export JARVIS_WORKSPACE="$HOME/Projetos"
mkdir -p "$JARVIS_WORKSPACE"
# Opcional: ID anunciado por jarvis-fcc --models
export FCC_MODEL="provedor/modelo"
jarvis-fcc --health
jarvis-fcc --models
jarvis-fcc --check-fcc
jarvis-fcc                 # terminal
jarvis-fcc --gui           # interface gráfica
jarvis-fcc --voice         # push-to-talk no terminal
```

`--check-fcc` executa inferência real e pode consumir cota. Use `FCC_TOKEN` somente no ambiente local, se necessário. Para outras pastas permitidas, defina `JARVIS_ALLOWED_DIRS` com caminhos existentes separados por `:`. O modo padrão autoaprova ações dentro das capacidades e raízes autorizadas; `--manual-approve` ativa confirmação por ação. Fechar uma janela mantém uma confirmação pontual porque ela pode conter alterações não salvas. `--auto-approve` permanece compatível. Revogação da sessão impede novas ações, sem desfazer uma chamada já enviada. Ações de entrada gráfica dependem de opt-in e permissões do portal GNOME.

## Testes e diagnóstico

```bash
python -m unittest discover -s tests -q
jarvis-fcc --desktop-info
jarvis-fcc --windows-diagnostic
jarvis-fcc --doctor
```

Os testes automatizados não comprovam comportamento físico no seu GNOME, FCC ou dois monitores. Consulte [arquitetura](docs/ARQUITETURA.md), [matriz de validação](docs/V1_DIAGNOSTICO.md), [acompanhamento](docs/V1_EXECUCAO.md) e [guia de uso e recuperação](docs/GUIA_DE_USO.md). O [README histórico](docs/README_HISTORICO.md) preserva os experimentos e instruções anteriores.

Atualização local sem apagar histórico SQLite: `git pull --ff-only`, ativar a venv e repetir `python -m pip install -e ".[desktop]"`. Faça backup do banco antes de atualizações importantes; a migração é versionada e não destrutiva.
