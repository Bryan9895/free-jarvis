# JARVIS FCC

Assistente pessoal em português para Ubuntu GNOME Wayland. A CLI e a GUI usam o mesmo núcleo para conversar com modelos do Free Claude Code (FCC), executar ferramentas locais autorizadas, organizar janelas e ambientes, trabalhar com arquivos e usar um navegador Chromium isolado. Esta branch prepara a v1.0; o pacote ainda declara **0.4.0** até passar todos os critérios de entrega.

## Instalação

O perfil **Engenharia FCC** continua sendo o padrão compatível. O primeiro
checkpoint do perfil **Local**, com Engine OpenJarvis/Ollama em processo isolado,
está disponível por seleção explícita. A comparação Gemma/Qwen e o aceite físico
offline estão pendentes; veja [preparo e validação Local](docs/PERFIL_LOCAL.md).

O provisionamento explícito agora pode ser feito com `jarvis-fcc local install-engine`.
Use `jarvis-fcc local status` para distinguir motor instalado, Ollama disponível e
inferência ainda não testada. O startup nunca instala esses componentes.

Requer Python 3.10+ e, no perfil FCC, um servidor FCC configurado separadamente. No diretório do repositório:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[desktop]"
jarvis-fcc --doctor
jarvis-fcc --doctor --doctor-format human
jarvis-show                 # mostra a janela existente ou inicia uma única GUI
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

Kokoro com `pf_dora` pode ser provisionado e selecionado em Configurações → Voz →
Saída, mantendo Piper como opção e padrão das instalações existentes. O adaptador
e os testes controlados estão implementados; síntese real e reprodução Bluetooth
aguardam dependências/pesos e aceite físico. Consulte [Kokoro local](docs/KOKORO_LOCAL.md).

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


### Evolução de conversa e autonomia

Respostas informativas chegam progressivamente; voz usa frases e pipeline
limitado. Parar cancela rede conectada/voz e descarta resultados atrasados. Voz →
Saída permite preparar Piper sem reproduzir. Pedidos que atingem o teto de áudio
ficam pendentes, com Continuação/Descarte explícitos, sem executar texto parcial.

Configurações → Permissões reúne concessões persistentes por categoria e pasta,
terminal e administração via autenticação nativa. Nenhuma concessão ampla é
habilitada silenciosamente. “Adicione às tarefas: …” executa localmente; pedidos
compostos continuam no executor/modelo. Detector acústico pt-BR aceito ainda não
acompanha o projeto; o fallback por transcrição permanece identificado.

Resultados, procedimentos e pendências físicas: [relatório de latência](docs/LATENCIA_2026-10-27.md)
e [validação por checkpoint](docs/VALIDACAO_CONVERSA.md).

Preparação explícita do Ollama, troca de perfil na GUI, diagnóstico, comparação
fria/aquecida, serviços de projeto e pendências reais estão descritos no
[checkpoint de implementação Linux](docs/IMPLEMENTACAO_LOCAL_2026-11-05.md).
Whisper agora usa somente pesos já presentes durante a conversa; prepare-os com
`jarvis-fcc local install-stt --model small`. A palma experimental é opcional em
Configurações → Voz e permanece desativada por padrão.

A próxima frente de engenharia acrescenta pós-condições explícitas aos processos
e uma jornada reproduzível de clone, dependência local, testes e retomada.
Consulte [execução verificada de projetos](docs/ENGENHARIA_VALIDACAO.md).

O avaliador de fala agora confere consentimento, WAVs, classes de duração, pausa
e números/negações, com preflight sem modelo e relatórios sem transcrições.
Veja [avaliação dos ouvidos e resultados reais](docs/AVALIACAO_OUVIDOS.md).

O adaptador Kokoro agora cobre cancelamento na espera e no envio ao worker,
recolhe o grupo de processos e publica somente WAV completo. O
[guia Kokoro](docs/KOKORO_LOCAL.md) inclui o ensaio de cancelamento sem player,
a baseline Piper real e as pendências de pf_dora.
