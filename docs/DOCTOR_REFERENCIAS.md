# Doctor: escopo do resultado e referência STT

Checkpoint de 06/11/2026, sobre `934170b6498c623e1aa4038f88e40a29e07b1a99`.

O Doctor mantém o JSON básico, a apresentação humana e os testes ativos
explícitos. O modo básico continua sem inferência, captura, player ou download.
Agora identifica o modelo STT e backend de voz efetivos e mantém configuração,
síntese, transcrição e execução do player em verificações separadas.

## Texto produzido não é referência conferida

O comando antigo permanece disponível:

```bash
jarvis-fcc --doctor --active-test stt --sample /caminho/externo/amostra.wav
```

Nesse modo, OK significa apenas que o reconhecedor produziu texto não vazio.
O resultado inclui `reference_check: "Não testado"` e a apresentação humana
explica que a acurácia não foi testada. Não se imprime a transcrição.

Para conferir uma referência dirigida e consentida:

```bash
jarvis-fcc --doctor --active-test stt \
  --doctor-corpus /caminho/externo/corpus.json --doctor-timeout 300 \
  --doctor-format human
```

O corpus usa o mesmo formato e validador da
[avaliação de ouvidos](AVALIACAO_OUVIDOS.md): consentimento explícito, WAV e
referências fora do Git, limites e fingerprints. `--sample` e `--doctor-corpus`
são alternativas; o corpus exige `--doctor --active-test stt`.

O teste de referência é estrito: para OK, todas as tentativas precisam executar,
WER lexical precisa ser zero e o critério crítico não pode falhar. Diferença
apenas de escrita, como algarismos versus números por extenso, pode reprovar o
critério literal apesar de a quantidade estar preservada. WER, estado/taxa
críticos e cobertura humana aparecem separadamente. Não se usa esse resultado
sozinho para escolher outro modelo ou julgar entendimento semântico.

Falha com texto produzido recebe `reference_mismatch`; erro de transcrição é
`transcription_failed`. Referências sem elementos críticos permanecem
`unmeasured`. Um resultado exato em fonte sintética pode passar funcionalmente,
mas a cobertura humana continua pendente. Nenhum resultado marca Bluetooth ou
áudio audível como aceito.

O prazo é de 1–300 s, 60 s por padrão, incluindo o ensaio no processo isolado.
Use um corpus pequeno; um conjunto longo pode atingir o prazo. Para comparação
extensa de beams, use o avaliador dedicado. Mudança do manifesto após a
solicitação é recusada. O relatório contém somente métricas e fingerprint, sem
referência, hipótese ou caminho privado do corpus. Segredos de configuração
continuam sendo enviados ao filho por stdin, não argv ou relatório.

## Configuração e resultado funcional

Um teste TTS atualiza `tts_synthesis`, não o estado de configuração `tts`.
Assim, presença/configuração, síntese realizada e player executado não são
confundidos. `audible` continua pendente de confirmação física. Kokoro exige
presença tanto de artefatos quanto de runtime para configuração OK; a presença
não comprova integridade, importação ou síntese.

O teste do player continua explícito com `--active-test playback`. Ele não é
executado pelo modo básico nem por `--active-test tts`.

## Temporários, timeout e saída WAV

Cada teste ativo recebe um diretório privado pertencente ao processo pai. Os
temporários Python do filho, incluindo captura solicitada explicitamente, ficam
nesse diretório. O pai encerra o grupo do teste antes de remover os arquivos,
inclusive no timeout. Dentro do teste, o worker Kokoro herda o grupo do Doctor;
os workers cotidianos da GUI/CLI continuam com sessão própria. Isso impede que
um worker de síntese escape da limpeza ao encerrar somente o diagnóstico.

```bash
jarvis-fcc --doctor --active-test tts --doctor-output /tmp/voz-nova.wav
```

A saída é preparada em arquivo temporário no filesystem do destino. O pai
confere o WAV completo e o publica atomicamente somente depois de sucesso, sem
substituir um destino concorrente. Áudio incompleto, timeout ou protocolo inválido
não publica o destino. O PCM16 pode ser mono/estéreo, 8–96 kHz, até 120 s e
64 MiB; quantidade de dados e cabeçalho precisam corresponder. Arquivos existentes
continuam recusados. Não houve alteração de seleção de voz ou permissões.

## Evidência real e pendências

O Doctor executou Whisper small sobre o mesmo arquivo sintético dirigido usado
no checkpoint anterior. Registrou falha de referência, WER 0,3846 e critério
crítico reprovado, sem falha de execução do reconhecedor. A cobertura humana
permaneceu pendente. Essa amostra não mede erro humano ou Bluetooth.

O teste TTS real gerou e publicou WAV Piper completo: 56.832 frames, mono,
22.050 Hz. O campo audível permaneceu não testado. Não houve microfone ou player
nesses dois ensaios. Relatório sanitizado em
[doctor-functional-2026-11-06.json](metrics/doctor-functional-2026-11-06.json).

Os testes controlados também comprovam que timeout encerra o processo de teste
e o worker de síntese no grupo herdado, remove temporários e não publica saída
parcial; um destino criado durante o ensaio é preservado.

Ollama e Kokoro seguem ausentes e a consulta DNS falhou neste ambiente. Faltam
provisionamento, corpus humano consentido, Bluetooth, Jarvis isolado e ensaio
físico offline. O Doctor não converte essas pendências em aprovação.
