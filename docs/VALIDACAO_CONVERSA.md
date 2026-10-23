# Validação incremental da conversa

Data: 2026-10-23. Aceite final **pendente**.

## Partida auditada

Checkout inicial `127cfed57bd3557bce6d8a838034e51291a09ad6`; remoto sincronizado por fast-forward para `9f63de9fe9391905cbcfc73533d9371d69dffcc0` (dois commits de documentação). Arquivos locais `modelos/` e `src/jarvis_fcc.egg-info/` preservados. O AGENTS recebido do remoto já contém as dez regras; atualização preserva-as e explicita precedência e evidências.

Baseline: `PYTHONPATH=src python -m unittest discover -s tests -q` executou 370 testes. No sandbox: quatro erros (sockets, Chromium, dois testes Tk). Fora do sandbox, com display real: um erro preexistente no E2E de abas: `browser.new_page()` cria contexto de página única e impede segunda aba no Playwright instalado. Os testes Tk passaram nessa execução. Sem testes ignorados.

## Cadeia atual e diagnóstico

CLI: `cli.main` → `JarvisService` → `MixedInput`/`run_voice_session` → `WakeWordConversation`. GUI: widgets → fila `GuiBackend` → serviço. Captura contínua: SoundDevice PCM16 mono 16 kHz, fila 64 × 80 ms, pré-fala 960 ms, RMS → WAV temporário → Whisper CPU int8 carregado sob demanda → regex inicial de ativação → serviço/FCC → Piper/aplay. Diagnóstico utiliza gravação temporária separada e pausa do listener. Nenhum detector acústico dedicado validado está instalado por este trabalho.

Falhas confirmadas por leitura: botão chama `record(6)`; contínuo termina em 15 s; seguimento de 20 s expira mesmo após início da fala; overflow descarta frames sem invalidar intenção. Não é possível atribuir a falha relatada no fone a um estágio sem ensaio consentido do dispositivo.

Configuração padrão no código: Whisper small na GUI contínua/botão, tiny no VoiceIO genérico; idioma pt; entrada SoundDevice/ambiente ou padrão; saída aplay padrão; Piper desativado sem modelo. Fonte PipeWire efetiva, conversa FCC, CPU/RSS e latências aquecidas: **pendentes de medição em sessão física**, sem captura ambiental automática nesta auditoria.

| Jornada | Estado inicial | Evidência / gate |
| --- | --- | --- |
| Fala livre no botão e contínuo | falhou | Cortes de 6/15 s confirmados no código |
| Suíte baseline completa | falhou | 370 testes, um erro E2E fora do sandbox |
| Layout Tk existente | passou | Dois testes GUI em display real; não prova áudio |
| Jarvis isolado | pendente | Sem artefato acústico validado; fallback STT + regex |
| Bluetooth e reconexão | pendente | Requer entrada física e fonte efetiva |
| Voz pt-BR audível | pendente | Exige modelo Piper e saída testada |
| FCC e efeitos GNOME | pendente | Exige inferência e observação de janelas reais |
| Latência/RSS por 30 turnos | pendente | Não medida; metas não são resultados |

## Procedimento físico de aceite

1. Abrir `jarvis-fcc --gui`; selecionar microfone em Voz → Microfone. Em Testar áudio gravar apenas a frase consentida, ouvir e transcrever com small. Apagar amostra ao terminar. Anotar entrada SoundDevice e fonte PipeWire separadamente.
2. Testar botão e contínuo com pedidos de 3, 10, 25 e 60 s, incluindo pausa interna de 800 ms. Verificar intenção inteira e envio único. Provocar desconexão e pressionar Parar; nenhum resultado antigo pode executar depois.
3. Para detector acústico futuro: registrar artefato/licença/hash, 20 chamadas “Jarvis” isolado (mínimo 18 acertos), 30 min negativos (máximo um falso positivo), ruído/distância. Não aceitar regex como prova desse gate.
4. Selecionar voz local pt-BR e saída; testar frase, texto longo e código. Confirmar ausência de autoativação. Medir primeiro áudio com TTS aquecido separadamente da carga inicial.
5. Pedir Firefox, tarefa e janelas lado a lado; observar efeitos. Simular FCC indisponível e saída errada: áudio, texto e provedor devem ter erros distintos, sem replay de efeitos.
6. Reiniciar, reconectar fone e repetir por 30 turnos. Registrar CPU/RSS, perdas, latência por estágio; testar 1040×640 e 1366×768 com escala GNOME aumentada. Nunca versionar áudio/transcrição ambiental.

Checkpoint 0: após corrigir o contexto do teste, a suíte completa passou: 370 testes em 5,728 s, sem ignorados, fora do sandbox com display real. `git diff --check` passou. Isso não valida voz ou FCC reais.

## Checkpoint 1 — captura e endpoint

Implementado: endpoint compartilhado botão/contínuo, pré-fala de 800 ms, silêncio por contagem de amostras (1 s padrão), teto emergencial de 120 s que rejeita o turno, overflow/status do backend invalidando áudio, exclusão global de captura no processo, duas retentativas com backoff e término manual no botão. Timeout de seguimento só antes de começar a fala. Parar durante captura/STT do botão descarta o resultado; diagnóstico fixo mantém rótulo de 6 s. Escuta e diagnóstico podem ser iniciados sem FCC conectado.

Automação **passou**: 378 testes em 5,882 s, incluindo Tk/Chromium e novos casos de 3/10/25/60 s, pausa de 800 ms, overflow, exclusão e recuperação limitada. `git diff --check` passou. Frames são sintéticos; não são arquivos de fala nem benchmark acústico.

Limites: RMS ainda é fallback, não VAD validado. Captura continua pedindo mono 16 kHz; negociação Bluetooth e timestamps/métricas por frame ainda pendentes. Áudio fica limitado a cerca de 3,84 MB PCM por turno a 16 kHz, mais overhead de arrays; teto rejeita em vez de manter intenção parcial para continuação. Detector dedicado, montagem segmentada, controlador canônico e cancelamento completo do TTS ainda não entregues neste checkpoint.

Publicação: shell HTTPS sem credencial; checkpoint 0 publicado via integração GitHub em `7c0d26ee83b63e7c194f7d6bd7d6a57d5b149f76`. Sem force push.

## Checkpoint 2 — controlador e fala

GUI (texto/voz), CLI mista e CLI contínua usam `ConversationController.run` → `JarvisService.ask`, sem segundo executor. Eventos tipados têm sessão, turno, motivo e tempo monotônico. Cancelamento invalida respostas atrasadas; falha de TTS preserva texto e não repete execução. `ResponseText` separa tela/fala por transformação determinística; código, tabela, JSON e caminhos não são pronunciados literalmente. Piper recebe segmentos sem corte de 3.000 caracteres. Player/síntese podem ser terminados e recolhidos no cancelamento. Persona adicionada às instruções existentes.

Limitações: controlador ainda começa na intenção textual; a máquina de captura/ativação permanece no adaptador legado. TTS ainda inicia Piper por segmento, sem cache residente da voz. Eventos não persistem conteúdo ambiental. Gate de áudio audível, latências aquecidas, interrupção acústica e modelo Jarvis continuam pendentes. Commit publicado do checkpoint de captura: `c0d1e35726053cf588f495749188c04181c90566`.

Automação do checkpoint 2 **passou**: 388 testes em 5,842 s; display real, Chromium e HTTP local incluídos. Novos testes: correlação, cancelamento, falha TTS sem replay, recuperação de provedor, formatter, ordenação longa e término/recolhimento de player falso. `git diff --check` passou. Não houve áudio gravado consentido nem ensaio acústico.

## Checkpoint 3 — preferências e interface

Implementado: preferências com esquema fechado v1, arquivo privado e substituição atômica, recuperação visível de arquivo inválido e precedência de ambiente. GUI salva voz local selecionada, sink Pulse/PipeWire, silêncio de 600–1800 ms, entrada, STT e modo; modelo FCC selecionado também persiste. Sem segredos nesse arquivo. CLI respeita modo salvo; `--voice` explicita contínuo. Piper local pode ser testado sem FCC; seleção de saída usa paplay e não muda o padrão global.

Início mostra conversa e controles; navegação e painéis ficam recolhidos em Configurações, preservando funções anteriores. Voz → Saída permite escolher `.onnx`, listar saídas, salvar e testar frase. O `.onnx.json` compatível e executáveis precisam existir. Instalação/download automático não implementado: licença/hash do artefato de voz ainda não verificados, nenhum modelo foi distribuído. Salvar entrada/modelo requer Aplicar na sessão contínua ou reinício; mudo/manual encerra listener ativo.

Automação **passou**: 394 testes em 6,547 s, incluindo persistência/erro atômico, ambiente, configuração sem FCC, STT tardio após stop e bounds Tk em 1040×640 e 1366×768. `git diff --check` passou. Escala maior GNOME, áudio audível e reinício físico Bluetooth continuam pendentes. Publicação anterior: `864ff6e3d41fe4e5cd9cb79508ee26e566e95d80`.

Como usar: `jarvis-fcc --gui` → Configurações → Voz → Microfone; em Saída selecionar modelo local e sink, Salvar, Testar voz salva. Em Conversar aplicar entrada/Whisper; Falar/terminar dispensa ativação. Contínuo usa fallback por transcrição identificado no estado; não é detector acústico aceito. CLI: `jarvis-fcc` mistura texto/voz conforme modo salvo, `--text-only` evita captura e `--push-to-talk` usa endpoint com revisão.

## Checkpoint 4 — formato, cache e integridade

Negociação consultada pelo SoundDevice tenta PCM16 mono 16 kHz e depois taxa/canais nativos (até estéreo). Downmix fica fora do callback. WAV registra taxa nativa para uma única decodificação/ressample no STT. Diagnóstico usa a mesma negociação. Callback contínuo copia/enfileira com timestamp monotônico; estatísticas em memória incluem frames, perda de turnos, pico de fila e atraso. Não muda fonte global. Modelo Whisper agora tem um cache global serializado: troca libera o anterior antes de carregar outro CPU int8; diagnóstico e conversa compartilham cache. Indicadores STT combinados de ausência de fala e logprob rejeitam turno incerto, sem blacklist textual. Isso não substitui um VAD acústico validado.

Automação **passou**: 401 testes em 7,159 s, incluindo negociação nativa/erro, cache/reuso/recuperação, STT incerto e jornada de frames sintéticos → STT controlado → efeito controlado único → resposta visual → remoção do WAV. Os testes não demonstram precisão de fala real.

Ensaio com artefato local (não distribuído): `modelos/piper/pt_BR-faber-medium.onnx`, SHA256 `858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7`. Piper instalado sintetizou frase controlada em WAV mono 22050 Hz, 57856 frames; retorno 0; 5,391 s incluindo processo/carga fria. Arquivo temporário apagado. Não foi reproduzido no fone; não é latência aquecida nem aceite de 2 s. Licença do artefato e download gerenciado continuam pendentes.

Publicação anterior de preferências: `45bf7a8b34124a06b3630050412da08dc01d3b7a`. Matriz atual: endpoint/integridade/cache/preferências/layout automatizados passaram; detector Jarvis, VAD acústico, voz audível, Bluetooth, efeitos GNOME/FCC reais, escala GNOME e latência/RSS aquecidas permanecem pendentes. Nenhum arquivo de áudio ambiental foi avaliado.

## Checkpoint 5 — Piper residente e cancelável

Síntese usa um processo Piper CPU residente, separado do player. Uma voz por processo principal; chamadas sequenciais reutilizam worker. Troca de voz, cancelamento, erro e timeout encerram/recolhem o worker e invalidam a conexão. Próximo turno pode recarregar. Carregamento é tardio; não ocorre download no startup. ONNX telemetry é desativada no worker.

Automação **passou**: 405 testes em 6,903 s, incluindo cache do worker, cancelamento, timeout e recuperação de voz inválida. `git diff --check` passou.

Ensaio real de síntese, sem reprodução: mesma frase controlada, mesmo artefato local/hash do checkpoint 4, mesmo processo nas duas chamadas. WAVs mono 22050 Hz: primeira chamada 3,739 s (57600 frames), segunda 0,234 s (58112 frames). Variação de frames é possível na síntese; ambos os arquivos foram removidos. Tempos são geração de WAV incluindo carga fria na primeira chamada; não medem player, primeiro áudio no fone nem p95. Meta aquecida de saída audível continua pendente.

Publicação anterior de formato/cache: `0317f93ce25076d602ebeee92c35c58bc112f384`.
