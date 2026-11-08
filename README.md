# ADAM — Assistente Digital Autônomo Modular

**ADAM é um assistente nativo de desktop em Python/Tkinter**, em português brasileiro.
Usa o mesmo motor de automação e memória do antigo Free-Jarvis, com o **FCC
como provedor de IA padrão**. Sua GUI principal é uma esfera de partículas
animadas no Canvas do Tkinter. **Não há servidor HTTP, navegador, HTML ou
JavaScript na interface.**

## Arquitetura

```text
Microfone (captura única + VAD) -----> faster-whisper -----> ADAM (personality)
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
sudo apt install python3-tk alsa-utils
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[voice,desktop]'
export FCC_URL=http://127.0.0.1:8082
export JARVIS_PROFILE=fcc
export ELEVENLABS_API_KEY="sua-chave"
adam --gui
# atalhos equivalentes: adam-show ou jarvis-fcc --gui
```

Na GUI: **“Adam”** ativa a conversa contínua por transcrição local; **segure
Espaço** ou o botão para falar manualmente; **T** abre o campo de texto;
**H** mostra ou esconde a conversa; **Esc** interrompe uma resposta.
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

- A ativação por **Adam** usa o caminho local de transcrição quando não há
  detector acústico treinado especificamente para essa palavra. Um
  detector treinado para “Jarvis” NÃO deve ser reaproveitado como “Adam”.
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
