# Revisão técnica: voz e autonomia

Data: 23/10/2026. Escopo: análise de documentação e arquivos centrais; sem executar os assistentes de referência ou validar seus dispositivos.

## Identidade das referências

O nome “MarkIV” usado na conversa corresponde à referência anteriormente indicada, **FatihMakes/Mark-LVI**. OpenJarvis é **open-jarvis/OpenJarvis**, não projetos homônimos de outros autores.

| Projeto | Snapshot examinado | Arquivos principais examinados |
| --- | --- | --- |
| [Mark-LVI](https://github.com/FatihMakes/Mark-LVI) | `4d4035c1b40a3bc796ac63f2f1b6a99bc0dd334d` | `readme.md`, `ui.py`, `main.py`, `core/wake_word.py`, `core/echo.py`, `providers/engine_pipeline.py`, `providers/tts_piper.py` |
| [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) | `4741d5d38875de0ea4e266e5daa1151e8f4a44c2` | `src/openjarvis/speech/voice_io.py`, `speech/tts.py`, `speech/_stubs.py`, `agents/tool_resolver.py`, `agents/loop_guard.py`, `core/events.py`, `LICENSE` |
| free-jarvis | publicado `127cfed57bd3557bce6d8a838034e51291a09ad6` | `voice.py`, `voice_session.py`, `gui.py`, `gui_voice.py`, `gui_models.py`, `service.py`, `agent.py`, `loop_guard.py`, `config.py` |

## O que as referências oferecem e como aproveitar

| Área | Evidência | Aplicação proposta no free-jarvis |
| --- | --- | --- |
| Ativação | Mark tem `WakeWordDetector`, fila limitada e inferência fora do callback. Seu modelo é `hey_jarvis`, não uma prova de reconhecimento de “Jarvis” isolado em pt-BR. | Detector dedicado, separado de STT, com medição real da palavra exigida. Nunca mudar silenciosamente o requisito para “Hey Jarvis”. |
| Fim de fala | Pipeline local do Mark acumula áudio e mede silêncio com piso adaptativo. `OpenJarvis/speech/voice_io.py` grava até silêncio; o snapshot usa 1,5 s e teto de 30 s. | Coordenador único com VAD e silêncio configurável de aproximadamente 1 s. Não copiar os tetos como duração de pedido. |
| Resposta falada | Mark separa STT/LLM/TTS e tem Piper, voz do sistema e outros provedores. OpenJarvis define contratos separados para síntese, resultado e health check. | Contrato de TTS com instalação/seleção/teste visíveis, reprodução na saída escolhida e erros próprios. Voz local como caminho principal. |
| Eco e interrupção | Mark tem `EchoGuard`. O próprio comentário diz que interrupção por voz depende de ensaio físico e permanece desligada nesse caminho. | Priorizar ausência de autoativação e botão Parar; barge-in é uma fase com evidência acústica, não funcionalidade garantida por existir uma classe. |
| Interface | Mark usa HUD e configurações em drawer. | Tela inicial centrada na conversa e controles essenciais; opções raras em uma área recolhida. Sem copiar assets ou adotar PyQt6 apenas por semelhança. |
| Execução | OpenJarvis separa resolução de ferramentas, eventos e proteção contra loops. | Evoluir o núcleo já existente, correlacionar turnos/ações e verificar efeitos. Não recriar registro/loop guard que o free-jarvis já tem. |

As referências mostram padrões úteis, não comprovam operação perfeita em Wayland, em português ou com o fone do usuário. OpenJarvis é um framework amplo; sua existência não implica wake word pronta neste caminho de captura.

## Diagnóstico do free-jarvis

| Problema | Evidência no código ou no relato | Consequência |
| --- | --- | --- |
| Pedido limitado a 6 s no botão | `gui.py`, ação `voice_push_to_talk`, chama `voice.record(6)`. `VoiceIO.record` também tem padrão 6. | Frase pode terminar fora da janela e ser enviada incompleta. |
| Ativação frágil | `WakeWordConversation` transcreve uma fala completa e depois aplica `WAKE_PATTERN` no começo do texto. | Precisão e latência do Whisper também controlam a ativação; não há detector acústico dedicado. |
| Contínuo já existe, mas não foi aceito fisicamente | `_listen_for_command` usa RMS e 1 s de silêncio. O usuário relata que não ativa. | A correção exige reproduzir a sessão e medir a cadeia, não afirmar que basta ativar o botão. |
| Outro limite pode cortar uma fala longa | `max_command_seconds=15`; `idle_timeout=20` durante seguimento é contado desde a abertura da captura, inclusive após começar a falar. | Mesmo fora do botão, turnos longos podem ser interrompidos. Timeout de espera e limite de armazenamento estão misturados. |
| Quadros podem ser descartados | A fila de `_listen_for_command` remove o item mais antigo quando enche. | Pressão de CPU pode perder trechos sem um erro explícito para o usuário. |
| Microfone Bluetooth/roteamento | Captura força mono 16 kHz; seleção SoundDevice e `PULSE_SOURCE` são camadas diferentes. | É preciso negociar formato/ressample e confirmar a fonte real. Uma entrada disponível não comprova fala chegando. |
| TTS opcional sem configuração fácil | `VoiceIO.speak` retorna `disabled` sem `JARVIS_PIPER_MODEL`; exige arquivo, `piper` e `aplay`. | Ter o pacote instalado não significa ter voz funcionando. |
| Texto visual enviado diretamente à voz | GUI encaminha a resposta a `speak`; não há representação própria para fala. Há ainda `text[:3000]` na síntese. | Markdown pode ser pronunciado e respostas longas são truncadas. Falta personalidade de conversa e segmentação sem cortes arbitrários. |
| Erro da IA confundido com áudio | Imagem do usuário contém fala recebida e 404 upstream NIM, função não encontrada para a conta. | Captura, transcrição e resposta precisam de estados independentes. Uma troca de Whisper não corrige NIM. |
| Interface expõe operação demais | Menu lateral mantém planos, tarefas, abas, janelas, permissões, ambientes, histórico, métricas, modelos e voz permanentemente. | A navegação continua orientada a administração, em vez de conversa. |

## O que preservar

Já há serviço compartilhado, exclusão/cancelamento, memória e planos SQLite, Toolkit, registro de ferramentas, permissões, execução verificada, loop guard, GUI/CLI e diagnóstico local. A autonomia deve compor essas peças. Um novo prompt, sozinho, não resolve captura, roteamento, instalação da voz ou lifecycle das threads.

## Fontes reproduzíveis

- [Wake word do Mark, snapshot](https://github.com/FatihMakes/Mark-LVI/blob/4d4035c1b40a3bc796ac63f2f1b6a99bc0dd334d/core/wake_word.py).
- [Pipeline local do Mark, snapshot](https://github.com/FatihMakes/Mark-LVI/blob/4d4035c1b40a3bc796ac63f2f1b6a99bc0dd334d/providers/engine_pipeline.py).
- [Echo guard do Mark, snapshot](https://github.com/FatihMakes/Mark-LVI/blob/4d4035c1b40a3bc796ac63f2f1b6a99bc0dd334d/core/echo.py).
- [Captura até silêncio do OpenJarvis, snapshot](https://github.com/open-jarvis/OpenJarvis/blob/4741d5d38875de0ea4e266e5daa1151e8f4a44c2/src/openjarvis/speech/voice_io.py).
- [Resolução de ferramentas do OpenJarvis, snapshot](https://github.com/open-jarvis/OpenJarvis/blob/4741d5d38875de0ea4e266e5daa1151e8f4a44c2/src/openjarvis/agents/tool_resolver.py).
- [Eventos do OpenJarvis, snapshot](https://github.com/open-jarvis/OpenJarvis/blob/4741d5d38875de0ea4e266e5daa1151e8f4a44c2/src/openjarvis/core/events.py).

Licenças examinadas: Mark-LVI declara CC BY-NC 4.0; OpenJarvis, Apache-2.0. A proposta usa design e implementação própria, sem importar os projetos como dependências.
