# Execução contínua para v1.0

Branch local: `work/v1-foundation`. HEAD de referência: `2043a4f`. Alterações geradas por instalação em `src/jarvis_fcc.egg-info/` são do ambiente e não serão versionadas. Publicação/push/PR dependem de autorização específica do usuário.

## Ordem de entregas recuperáveis

1. Diagnóstico, mapa de módulos e critérios de v1.0: `V1_DIAGNOSTICO.md`.
2. Contrato de resultados e evidência; validação de argumentos e proteção contra ciclos; testes de integração agente/registro/planejador.
3. Cancelamento cooperativo, retomada e migração SQLite não destrutiva.
4. Robustez de FCC, desktop, arquivos e navegador com regressões específicas.
5. Serviço de aplicação comum para CLI/GUI, GUI opcional e voz sob demanda.
6. Matriz de testes, medições reproduzíveis, documentação curta e decisão de versão.

Cada item recebe commit local após testes pertinentes. A ordem pode mudar quando um teste demonstrar dependência técnica. Não instalar extensões do sistema nem modificar configuração global.

## Estado da execução

- Inspeção: concluída; 282 testes iniciais passaram. `jarvis-fcc --desktop-info` detectou GNOME Wayland e portais, sem testar ações físicas.
- Etapa 1: diagnóstico e mapa concluídos em `V1_DIAGNOSTICO.md`.
- Etapa 2: contrato em `execution_result.py` classifica retornos em verificado, não verificado, parcial, recusado, indisponível, ausente, ambíguo ou falha; preserva o estado especializado. Agente expõe a classificação em `tool_outcomes`, e planejador interrompe continuidade após efeito enviado sem verificação. Nenhuma frase da resposta do modelo comprova execução. 286 testes passaram após a mudança.
- Etapa 3: argumentos passam pelo subconjunto JSON Schema usado no catálogo antes de autorização/execução; cancelamento cooperativo impede novas chamadas e marca etapa interrompida, sem alegar desfazer ações já enviadas; repetição AAA e ABABAB é interrompida por `LoopGuard`. 294 testes passaram após essas mudanças.
- Etapa 4/8: `database.py` migra bancos legados sem apagar linhas e cria eventos de execução sanitizados; `task_id` e `step_id` correlacionam chamadas de ferramenta. Escritas agora recebem conferência de arquivo/hash na execução e passam a evento `verified`. `JarvisService` oferece núcleo compartilhado a CLI/GUI. 305 testes passaram.
- Etapas 9–11: navegador tem timeout do subprocesso, fechamento de recursos, verificação do preenchimento/captura e detecção de mudança após clique; teste real com página controlada passou. Voz detecta silêncio, lista microfones sob demanda e permite corrigir transcrição na GUI. A GUI Tkinter compartilha `JarvisService` com a CLI, usa worker para FCC/SQLite e oferece chat, plano, permissões, perfis, histórico, métricas, seleção de modelo, voz e cancelamento. Smoke test inicial de GUI no GNOME usou serviço simulado; suíte daquele checkpoint: 300 testes.
- Etapa 3/5: operações de arquivo/comando foram extraídas para `filesystem_tools.py`, mantendo `Toolkit` como fachada de compatibilidade; `ModelProvider` formaliza o contrato de Responses/modelos. Arquitetura real e limites foram documentados em `ARQUITETURA.md`. Suíte: 308 testes passaram.
- Etapa 6: planos agora aceitam dependências explícitas entre etapas, validam referências anteriores e só executam dependentes após sucesso verificado. Planos históricos com descrições em texto continuam aceitos sem migração; uma etapa reportada sem verificação bloqueia dependentes. Regressões adicionadas; suíte completa: 310 testes passaram.
- Ambiente de desenvolvimento preparado: dependências opcionais browser/desktop/vision/voice e Piper no `.venv` e `.venv311`; Python 3.11.16 isolado no `.venv311`. A suíte completa (310) e E2E do navegador passaram no Python 3.11.16 e a suíte passou no Python 3.14.4. Piper gerou WAV válido pt-BR e faster-whisper tiny o transcreveu localmente; modelo `pt_BR-faber-medium` instalado em `~/.local/share/jarvis/voices` (modelo CC0). Dispositivos de captura enumerados via PipeWire/PulseAudio; gravação com fala real do usuário continua pendente.
- FCC foi testado contra o servidor real: health/modelos passaram; `--check-fcc` revelou e corrigiu `input` em formato incorreto, depois respondeu `OK`. Chat real completou em 2,17 s. Com `nvidia_nim/openai/gpt-oss-20b`, escrita real em workspace temporário foi concluída e conferida por SHA-256 em 9,86 s; `openai/gpt-5.6-luna` produziu texto com pseudo tool-calls, agora detectado sem executar nada. Plano real com inventário de ferramentas explícito criou e verificou arquivo em uma etapa em 16,85 s; antes dessa instrução o modelo sugeriu incorretamente que não havia ferramenta e a execução foi bloqueada sem alteração.
- Etapa atual: 5/6/13 — contrato e eficiência do FCC avançaram, incluindo categorias de erro, rejeição de pseudo tool-calls, catálogo reduzido e verificação de escrita. Retomada após interrupção tem testes de persistência; falta validação com processo encerrado durante operação real. GUI real com FCC ainda não foi ensaiada nesta sessão.
- Decisão: migração gradual, preservando nomes de módulos/comandos existentes; Tkinter substitui a proposta PySide6 por já estar instalado e não adicionar dependência em notebook de 8 GB. README atual foi reduzido e o histórico anterior preservado em `README_HISTORICO.md`.
- Falhas iniciais: avisos de HTTPError foram eliminados fechando respostas; coroutine de teste não aguardada foi eliminada fechando corrotinas simuladas. O diálogo real de salvamento continua sem validação física.
- GUI real com FCC: resposta `GUI_OK` em 1,63 s; RSS máximo medido 45.272 KiB durante a conversa. `--doctor` fora do repositório: mediana 0,152 s em cinco execuções. Ambiente: Ubuntu x86_64, Python 3.14.4, GNOME 50.1, 7.2 GiB RAM. A suíte agora passou em Python 3.14.4 e 3.11.16; workflow remoto não foi acionado.
- Validação física adicional: GNOME confirmou centralização de janela Tk e layout lado a lado de duas janelas Tk com `geometry_verified`/`layout_verified`; títulos com sobreposição foram recusados como ambíguos. Nesta continuação, movimento de janela Tk temporária entre HDMI 1920×1080 e eDP 1366×768 retornou `window_monitor_verified`. Firefox privado e VS Code com perfil descartável ficaram lado a lado com `layout_verified`; as janelas/processos de teste foram fechados. Diálogo de salvamento e push-to-talk com gravação/transcrição ainda pendentes.
- Inventário GNOME atual: HDMI 1920×1080 no índice 1 e eDP 1366×768 no índice 0; duas áreas de trabalho. Teste FCC final de escrita com catálogo reduzido anunciou uma ferramenta e concluiu/verificou em 4,33 s.
- Próxima ação concreta no ambiente físico: validar diálogo real de salvamento e push-to-talk com fala do usuário. GUI com tarefa longa/cancelamento via FCC segue como ensaio pendente. Nesta continuação, navegador E2E local, retomada e backend GUI passaram novamente. Instalação de CLI foi verificada fora do diretório do projeto nas duas versões de Python.
- 22/10/2026 — GUI/voz autônoma: aba Voz agora oferece ativação contínua por sessão. VAD segmenta fala e Whisper base verifica a palavra localmente; apenas transcrições iniciadas por Jarvis/Jarves (incluindo formas fonéticas vistas no Whisper) são enviadas ao FCC. A fala é temporária e seu WAV é removido após transcrição. Após a resposta, há até 20 s para continuar sem wake word; Piper fala a resposta se configurado. Adicionados testes de segmentação, filtragem de wake word e caminho do comando pela GUI. O detector pré-treinado Hey Jarvis foi avaliado com áudio Piper e não reconheceu “Jarvis” isolado; por isso a versão atual usa STT local em vez desse detector. O teste sintético Piper + Whisper base transcreveu como “Davies abrou Firefox”, reconhecido como wake word; precisão com a voz real e custo de CPU/RAM precisam de validação pelo usuário. Ainda não há validação física desse fluxo com microfone.
- Validação automatizada da mudança de voz: 14 testes focados passaram no Python principal; a suíte completa com 315 testes passou em Python 3.11 e 3.14. Pendente: captura com voz real, conversa encadeada e reprodução física da resposta Piper. O modelo base está no cache após o ensaio sintético; custo de CPU/RAM não foi medido.

## Continuação — 23/10/2026: confiabilidade da captura de voz

Branch: `work/voice-capture-reliability`; referência: `bf5e580`.

- Base: 315 testes executados com sucesso (um ignorado).
- Relatos do usuário: entrada virtual selecionada por índice variável; captura sem retorno; incompatibilidade faster-whisper 1.2.1/PyAV 19; áudio Bluetooth reproduzido com clareza, mas transcrição tiny/base imprecisa.
- Captura curta passa a usar callback e prazo de duração + 3 segundos. Dispositivo sem entrega de quadros retorna erro recuperável e o stream é abortado/fechado. O prazo cobre a espera por quadros; abertura/fechamento ainda dependem do backend de áudio.
- Escuta contínua herda o dispositivo da instância VoiceIO quando não há substituição explícita.
- Extra voice limita PyAV a >=11,<19 para evitar o argumento metadata_errors removido na versão 19. Validar novamente o limite ao atualizar faster-whisper.
- Não houve teste de microfone, Bluetooth, Piper ou FCC nesta máquina; testes de captura usam backend simulado. Nenhuma melhoria de precisão foi comprovada.

Próximas entregas, em ordem:
1. Recuperação da escuta contínua após erro de STT e diagnóstico de entrada sem quadros; seleção de dispositivo por nome inequívoco nas interfaces.
2. Ensaio de qualidade com áudio do usuário: comparar base/small sobre a mesma gravação e medir latência, sem enviar áudio ao FCC.
3. Cancelamento GUI/FCC e retomada após encerramento real, preservando operações incertas.
4. Perfil em dois monitores e diálogo de salvamento; atualizar matriz de aceite e decidir versão somente após evidências.

## Próxima entrega — recuperação e seleção de entrada (23/10/2026)

- Escuta contínua captura `VoiceError` da transcrição por fala, remove o WAV e retorna à espera da palavra de ativação. Não encerra a sessão por um trecho sem reconhecimento e não o envia ao FCC.
- Captura contínua informa erro se não recebe quadros por três segundos; stream é fechado pelo contexto. Backend travado na abertura/fechamento ainda não possui isolamento em subprocesso.
- CLI: `--audio-devices` sem inicializar FCC e `--audio-device NOME` para CLI/GUI. GUI usa nome em vez de índice exibido, mantém entrada padrão até escolha explícita e respeita modelo/idioma configurados na gravação curta.
- Suíte: 324 testes executados sem falhas, um ignorado. Inclui recuperação após erro com remoção dos WAVs, falta de quadros, seleção por nome e enumeração sem FCC. Hardware/FCC/GUI gráfica não foram ensaiados neste ambiente.
- Próximo passo: validação física Bluetooth nas duas interfaces e comparação base/small sobre o mesmo áudio. Depois, cancelamento com FCC e retomada após queda real; não declarar v1 concluída antes da matriz de aceite.
