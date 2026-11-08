# ADAM — Assistente Digital Autônomo Modular

**ADAM é um assistente nativo de desktop em Python/Tkinter**, em português brasileiro.
Usa o mesmo motor de automação e memória do antigo Free-Jarvis, com o **FCC
como provedor de IA padrão**. Sua GUI principal é uma esfera de partículas
animadas no Canvas do Tkinter. **Não há servidor HTTP, navegador, HTML ou
JavaScript na interface.**

## Arquitetura

```text
Espaço segurado (captura exclusiva) --> faster-whisper --> ADAM (personality)
       |                                                       |
       +-----> RMS (Tkinter Canvas)                    JarvisService / Agent
                                                               |
                                                    FCC (padrão) / Ollama (opcional)
                                                               |
                                                    ferramentas GNOME, arquivos,
                                                    planos, SQLite e automações
                                                               |
                            ElevenLabs TTS (internet) <---- texto em frases
                                       |
                            PCM 16k -> WAV -> paplay/aplay
                                       |
                            medidor de áudio -> esfera Tk
```

**Por que existe Ollama?** É uma opção **explicitamente selecionada** para
rodar modelos locais no computador, em vez de acessar o servidor FCC.
Não é necessário instalar ou iniciar Ollama para usar FCC. Um Orange Pi
com Linux e recursos suficientes poderá executar parte do sistema;
um ESP32 é adequado como módulo de sensores, LEDs, microfone ou transporte,
mas não como computador de inferência de LLM grande.

**Importante:** “interface local” não significa “100% offline”. ElevenLabs
usa serviço de nuvem, exige `ELEVENLABS_API_KEY`, internet e possui limites
de uso. FCC pode depender de provedores remotos. Para operação **totalmente
offline** no robô, será necessário escolher outro TTS local futuramente.

## Instalar e iniciar no Ubuntu

Requer Python 3.10+, Python Tkinter do sistema e um servidor FCC configurado.

```bash
sudo apt install python3-full python3-venv python3-tk libportaudio2 libsndfile1 pulseaudio-utils alsa-utils
bash tools/install_ubuntu.sh
source .venv/bin/activate
export FCC_URL=http://127.0.0.1:8082
export JARVIS_PROFILE=fcc
export ELEVENLABS_API_KEY="sua-chave"
adam --gui
# também é possível testar a interface SEM microfone e SEM chave:
adam --gui --text-only
# atalhos equivalentes: adam-show ou jarvis-fcc --gui
```

Na GUI: **segure ESPAÇO para gravar** e **solte para enviar a fala ao Whisper/FCC**.
Não existe escuta contínua, wake word por “Adam” ou botão de gravação por
clique nesta versão. **T** abre o campo de texto, **H** mostra/esconde a
conversa e **Esc** interrompe uma resposta. A interface precisa estar com o
foco do teclado, sem o campo de texto selecionado.
Configurações permitem alterar o ID do modelo FCC anunciado no catálogo.
Os comandos antigos `jarvis-fcc`, `jarvis` e `jarvis-show` permanecem
como aliases de compatibilidade. O pacote chama-se `adam-assistant`, mas
o módulo Python continua sendo `jarvis` para preservar dados e integrações.

### Chave e voz ElevenLabs

```bash
export ELEVENLABS_API_KEY="sua-chave"
export ELEVENLABS_VOICE_ID="pNInz6obpgDQGcFmaJgB"
export ELEVENLABS_MODEL_ID="eleven_flash_v2_5"
```

Esta versão prioriza ElevenLabs. Piper/Kokoro não são chamados pela interface
ADAM. Os módulos antigos permanecem temporariamente no repositório por
compatibilidade com versões anteriores; `piper-tts` não é mais instalado
como dependência. A voz não funciona sem internet/chave, mas o texto e o
motor FCC continuam funcionando.

### Personalidade

A personalidade padrão está em `src/jarvis/personality.py`. Você pode
escrever instruções próprias (sem publicar informações pessoais) em um
arquivo UTF-8 e informar:

```bash
export ADAM_PERSONA_FILE="$HOME/Documentos/adam-persona.md"
```

A identidade padrão é calma, objetiva, natural, com humor discreto,
sem repetição de saudações e sem promessas de execução não verificada.

### Opções

```bash
export ADAM_PARTICLES=960  # reduza para 500 no Orange Pi
export ADAM_FPS=30         # reduza para 20 se necessário
jarvis-fcc --doctor --doctor-format human
jarvis-fcc --models       # modelos FCC conhecidos
adam --profile local      # seleciona perfil Ollama/OpenJarvis, quando preparado
```

### Restrições atuais

- A ativação acústica por **Adam** está **desativada na GUI**. Nenhum
  detector contínuo abre o microfone em segundo plano. O suporte a wake word
  permanece somente como código legado/futuro, sem uso nesta interface.
- A esfera mede RMS do microfone na captura exclusiva. Na fala, anima com
  a amplitude do WAV reproduzido (aproximação; não é medição acústica).
- Testes automatizados não substituem validação real de Wayland, Bluetooth,
  microfone, ElevenLabs, FCC ou desempenho no dispositivo.
- A automação de navegador por Playwright, caso instalada, é uma *ferramenta
  do assistente* e **não** a interface gráfica.
- SQLite e variáveis `JARVIS_*` permanecem para evitar perda de históricos
  e quebrar instalações existentes. Renomear pastas e o repositório remoto
  exige uma migração separada.

Ver documentação técnica em `docs/ARQUITETURA.md` e `AGENTS.md`.

## Marcos de implementação (v0.5.0)

- **Instalação**: `tools/install_ubuntu.sh` cria e instala o venv sem modificar o Python gerenciado pelo Ubuntu.
- **Desktop**: interface Tkinter nativa, permissões por diálogo seguro, configuração persistente de modelo/perfil/ElevenLabs/persona e modo texto sem microfone.
- **Voz**: ElevenLabs exclusivo por padrão; `paplay` preferido em PipeWire/PulseAudio, especialmente Bluetooth.
- **Diagnóstico**: `adam --doctor --doctor-format human` distingue presença da chave ElevenLabs de ensaio físico de áudio.
- **Robô**: contrato de transporte simulado e seguro em `robot_transport.py`; nenhum motor nem serial real é ativado.
- **Latência**: UI registra tempo até o primeiro delta e duração total; metas de subsegundo ainda não foram comprovadas no seu PC.
- **Não concluído**: wake word acústico dedicado, barge-in por voz sem pressionar botão, Orange Pi/ESP32 físicos, operação 100% offline e ajuste fino medido no hardware.

### Modo temporário de voz: segurar Espaço

O ADAM agora só grava enquanto a tecla **Espaço** estiver pressionada.
Soltar a tecla finaliza o WAV; não há VAD ou janela fixa de 6 segundos.
Um limite técnico de 10 minutos descarta gravações excessivas em vez de
executar pedidos incompletos. Se a finalização ultrapassar 12 segundos,
a interface mostra erro de tempo limite, sem permanecer eternamente no estado
“Finalizando…”. Se houver outra instância do ADAM com o microfone aberto,
ela precisa ser fechada antes de testar.

A captura manual independe da chave ElevenLabs: Whisper transcreve localmente,
FCC responde por texto e ElevenLabs lê a resposta se tiver credencial válida.

Para executar com chave **sem salvá-la no repositório ou histórico do shell**:

```bash
bash tools/start_adam.sh
```

A chave ElevenLabs deve ser criada **na sua conta** em Developers → API Keys,
com permissão Text to Speech e limite de créditos recomendado. O script
solicita a chave sem ecoar sua digitação e a entrega apenas ao processo ADAM;
não grava credenciais em disco. Sem chave, a voz falada não será produzida.
