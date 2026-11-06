# Avaliação do fim de fala em WAV consentido

Checkpoint de 06/11/2026 sobre `9f3be6ba1af48dea694259c99e244b51c73be285`.

O ensaio complementa a [avaliação STT](AVALIACAO_OUVIDOS.md). Transcrever o
arquivo inteiro não revela onde o detector teria encerrado o pedido. Este replay
usa `PCMNormalizer`, `SileroActivity` e `AudioEndpoint`, os mesmos componentes
da captura cotidiana, com blocos nativos equivalentes a 80 ms e saída mono
16 kHz. O VAD é local e não baixa pesos. Não carrega Whisper, captura microfone,
reproduz áudio, chama modelo de conversa ou executa ferramentas.

## Uso

Use o mesmo manifesto externo consentido do avaliador STT. Todo o corpus é
validado antes de carregar VAD: consentimento, origem declarada, WAV completo,
formato, tamanho e referências fora de Git. As referências não são transcritas
nem comparadas neste ensaio; permanecem necessárias ao formato compartilhado.

```bash
PYTHONPATH=src python -m jarvis.endpoint_evaluation \
  /caminho/externo/corpus.json --output /tmp/endpoint-novo.json
```

O padrão usa silêncio de 1.000 ms, limiar VAD de 0,5, pré-fala de 800 ms e teto
de segmento de 120 s. Parâmetros explícitos `--silence-ms`, `--vad-threshold` e
`--max-seconds` permitem comparar o comportamento; não alteram preferências.
Para reproduzir outra configuração, informe seus valores efetivos. Os padrões
do ensaio são fixos, não uma leitura automática das preferências do aplicativo.

EOF não finaliza o turno. Quando o arquivo termina antes do silêncio necessário,
o resultado é `endpoint_not_reached`. Para um experimento separado, pode-se
acrescentar silêncio sintético deliberadamente:

```bash
PYTHONPATH=src python -m jarvis.endpoint_evaluation \
  /caminho/externo/corpus.json --tail-silence-ms 1500 \
  --output /tmp/endpoint-com-silencio-novo.json
```

`tail_silence_ms` registra a quantidade acrescentada e `endpoint_in_padding`
indica se a decisão dependeu dela. O arquivo original não muda. Não se apresenta
esse silêncio como áudio capturado nem se usa isso para completar cobertura
humana. Use destinos novos: o relatório completo é publicado atomicamente sem
substituir arquivos existentes ou criados concorrentemente.

## Interpretação

O replay continua analisando o arquivo após o primeiro endpoint, sem abrir outro
turno. Isso permite observar atividade que ficaria depois da primeira decisão.

| Resultado | Significado técnico |
| --- | --- |
| `passed` | Houve atividade na fonte, endpoint e nenhuma atividade posterior na fonte segundo o mesmo VAD |
| `activity_after_endpoint` | Há blocos ativos após a decisão; possível corte ou mais de um turno no arquivo |
| `endpoint_not_reached` | Atividade encontrada, mas o silêncio disponível não encerrou o turno |
| `no_activity` | VAD não marcou atividade na fonte; silêncio acrescentado não torna o ensaio válido |
| `segment_limit` | Teto atingido; segmento permanece pendente e não produz intenção executável |

`passed` não garante intenção completa ou acerto do VAD. Ruído pode causar
atividade e fala real pode não ser detectada. Um arquivo com vários turnos pode
legitimamente ter atividade após o primeiro endpoint. O alerta exige revisão do
corpus, não aumento automático do silêncio. Nenhuma configuração muda com base
nesses resultados. Falha de qualquer amostra retorna código 1, preservando o
relatório técnico; corpus inválido/alterado invalida o relatório inteiro.

O JSON identifica manifesto e áudios por SHA256; informa atividade inicial/final,
posição da decisão no áudio, blocos ativos posteriores, contagem normalizada e
estado pendente. Não contém caminhos privados, referência, hipótese, áudio ou
mensagens de erro do runtime. A contagem retida é somente uma medida; nenhum
áudio intermediário é persistido. `wall_s` mede processamento após inicializar
normalizador/VAD, sem simular tempo real e sem medir latência de captura.

O replay não exercita SoundDevice, relógio de captura, filas/overflow, ativação,
cancelamento do listener, envio ao controlador ou retomada de segmentos. O bloco
final e o flush de um WAV podem diferir do stream contínuo. Os testes cotidianos
desses caminhos continuam separados. Bluetooth, acurácia STT e entendimento
semântico permanecem não testados por esta ferramenta.

## Evidência deste checkpoint

O Silero real processou o arquivo sintético Piper do checkpoint anterior e duas
montagens dirigidas desse mesmo arquivo, sempre fora de Git. Sem microfone,
player, Whisper ou rede:

| Caso | Resultado |
| --- | --- |
| WAV original de 4,365 s, sem padding | `endpoint_not_reached` |
| Mesmo WAV + 1.500 ms de silêncio sintético | Endpoint aos 5,325 s, dentro do padding, sem atividade tardia |
| Duas cópias separadas por 800 ms acrescentados + padding final | Endpoint somente aos 10,571 s, após os dois trechos; sem atividade tardia |
| Duas cópias separadas por 1.400 ms acrescentados + padding final | Endpoint aos 5,359 s; 53 blocos ativos posteriores; alerta de possível corte |

Os intervalos acrescentados se somam ao silêncio já existente no WAV. Não são
medidas de pausas humanas. A fonte continua `synthetic`, com cobertura humana
pendente em todos os casos. Métricas sanitizadas em
[endpoint-replay-2026-11-06.json](metrics/endpoint-replay-2026-11-06.json).

Os testes controlados verificam fala de 3/10/25/60 s, pausa interna de 800 ms,
limite pendente, ausência de atividade, EOF sem finalização, resample estéreo
44,1 kHz com flush, alteração de corpus e publicação exclusiva do relatório.
Esses casos não são gravações de fala humana. Permanecem necessários corpus
humano consentido, captura Bluetooth, Jarvis isolado, Kokoro/Ollama reais e
jornada física offline antes do aceite do projeto.
