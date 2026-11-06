# Avaliação dos ouvidos — 05/11/2026

Esta etapa prepara e exercita a avaliação de reconhecimento pt-BR. Não altera
Whisper small/CPU int8, beam 5, VAD, captura cotidiana ou modelo de conversa.
Whisper continua usando somente pesos em cache durante a conversa.

## Corpus dirigido e consentido

Áudio e transcrições de referência ficam fora de repositórios Git. Não se procura
áudio no computador nem se grava o microfone ao executar o avaliador. Prepare um
JSON externo com a estrutura antiga ou os campos adicionais abaixo:

```json
[
  {
    "audio": "pedido-3s.wav",
    "reference": "Não apague dois arquivos.",
    "consent": true,
    "source_kind": "human",
    "duration_class": 3
  },
  {
    "audio": "pedido-com-pausa.wav",
    "reference": "TEXTO EXATO DA FALA DIRIGIDA",
    "consent": true,
    "source_kind": "human",
    "duration_class": 10,
    "pause_ms": 800
  }
]
```

Os nomes e frases são exemplos; não atestam que arquivos existem nem que uma
gravação tem aquela duração. Faça também as amostras de 25 e 60 s, com pedidos
completos, números, negações e pausa natural. A duração é a do WAV, incluindo
silêncios; a classe admite ±10%, com mínimo de ±300 ms. Não corte uma fala para
encaixá-la na classe. Registre uma nova amostra completa quando necessário.

`source_kind` aceita `human`, `synthetic` e `unspecified`; o padrão de manifestos
antigos é `unspecified`. Origem humana e consentimento são declarações do
responsável pelo corpus, não inferências acústicas. A cobertura dirigida exige
classes 3/10/25/60, pausa, números e negações em amostras declaradas humanas.
Corpus sintético nunca completa essa cobertura.

Cada arquivo precisa ser WAV PCM16, mono ou estéreo, 8–96 kHz, até 10 minutos e
64 MiB. O manifesto aceita até 200 amostras e 4 MiB. Referências precisam ser
não vazias e limitadas. `sha256` opcional permite conferir uma identidade já
registrada. Arquivos truncados, falta de consentimento, duração incoerente e
mudança do áudio/manifesto durante a avaliação invalidam o ensaio.

## Validação sem carregar modelo

```bash
PYTHONPATH=src python tools/evaluate_stt.py /caminho/externo/corpus.json \
  --preflight --output /tmp/preflight-stt.json
```

A pausa declarada de 800 ms exige um trecho interno de nível baixo entre
700 e 900 ms, com sinal antes e depois, em blocos de aproximadamente 20 ms.
O limiar RMS é apenas uma conferência de nível: não comprova fala, Silero/VAD,
pausa semântica ou fim de intenção. Silêncio inicial/final não satisfaz esse
critério. O ensaio de endpoint e a captura Bluetooth continuam separados.

O preflight verifica todo o corpus antes de qualquer carga de Whisper. Diretórios
Git reais e arquivos `.git` de worktrees são recusados. Diretórios `.git` vazios
criados pelo ambiente de permissões não são confundidos com um repositório.

## Transcrição e métricas

```bash
PYTHONPATH=src python tools/evaluate_stt.py /caminho/externo/corpus.json \
  --model small --beams 5 3 1 --repetitions 2 --output /tmp/stt-metricas.json
```

Beams são alternados por amostra/repetição para reduzir viés de ordem. Existe um
único modelo residente no processo. `JARVIS_WHISPER_MODEL` conflitante com
`--model` é recusado antes da inferência. Nenhum modelo é escolhido ou salvo
automaticamente com base no ensaio.

O JSON versão 2 preserva WER, contagem de falhas, medições e tempos aquecidos;
adiciona fingerprints, duração/formato, cobertura humana e RSS/PSS da árvore.
O tempo por tentativa mede transcrição, incluindo a carga sob demanda na primeira
tentativa de uma CLI nova; hashing e cálculo de WER ficam fora desse intervalo.
Não se limpa cache de disco do SO. Amostras pequenas não sustentam uma estimativa
estável de p95 nem uma recomendação de modelo.

Não são persistidos caminhos privados, referência, hipótese ou mensagens de
erro do reconhecedor no relatório. Erros são contabilizados sem reproduzir seu
conteúdo. A saída é gravada atomicamente e não pode substituir manifesto ou áudio
do próprio corpus. As métricas podem ficar no Git; WAVs e transcrições não.

## Critérios críticos

O comparador anterior só reconhecia algarismos. Agora verifica um subconjunto
conservador de quantidades por extenso, algarismos, decimais pt-BR, sinal negativo,
ordinais comuns e negações. Exemplos: `duas` e `2`, `vinte e três` e `23`,
`menos dois vírgula zero cinco` e `-2,05`. Códigos com zeros iniciais permanecem
distintos. Milhões/bilhões são marcadores de escala; não há uma equivalência
aritmética geral para toda expressão natural.

A sequência conjunta e o contexto próximo das negações também são conferidos,
para detectar deslocamentos como “não abra duas abas e abra três pastas” versus
“abra duas abas e não abra três pastas”. O resultado é uma heurística restrita,
não um avaliador semântico completo. Compare WER e revise os casos humanos; não
trate uma taxa crítica perfeita como prova de todas as intenções.

O relatório separa igualdade de números, negações, ordem crítica e contexto.
Uma transcrição que falhou nunca passa nessa checagem. Sem referência contendo
elemento crítico, a taxa é `null` e o estado é `unmeasured`, em vez de 100%.
WER continua lexical: escrever `23` em vez de `vinte e três` pode aumentar WER
mesmo quando a quantidade foi preservada.

## Ensaio técnico executado

Uma frase dirigida foi sintetizada pelo Piper já instalado, em arquivo externo,
sem player ou microfone. WAV mono a 22.050 Hz, 4,365 s, fonte `synthetic`.
Whisper small/CPU int8, beam 5 e VAD ligado fizeram duas transcrições reais com
pesos locais. Primeira tentativa 8,051 s; tentativa aquecida 5,474 s. Pico PSS
846.408 KiB; apenas um modelo Whisper, sem Piper residente durante STT.

**Não passou no critério de quantidades:** taxa crítica 0/2. A negação e seu
contexto próximo foram preservados nas duas tentativas; números e sua ordem
divergiram da referência. Não houve falha de execução do reconhecedor. Isso é
resultado de um único arquivo sintético, não taxa de erro humana ou Bluetooth.
Não se alterou modelo, beam, VAD ou default com base nessa amostra.

Métricas sanitizadas em
[stt-synthetic-2026-11-05.json](metrics/stt-synthetic-2026-11-05.json).
WAV e referência continuam fora do Git. Faltam corpus humano consentido, endpoint
em fala real, Bluetooth, Jarvis isolado, Kokoro e os turnos físicos finais. Kokoro
continua sem runtime/pesos, com provisionamento bloqueado por DNS nesta sessão.
