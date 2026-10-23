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
