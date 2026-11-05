# Implementação Linux — 05/11/2026

Base publicada: `18e385a21e57c906f033f93631a942755bd52616`.
Este checkpoint implementa a infraestrutura abaixo; o aceite completo do plano
permanece pendente. As alterações locais anteriores de equipe foram preservadas.

| Frente | Entrega verificável | Aceite ainda pendente |
| --- | --- | --- |
| Preparação Local | Ollama Linux por usuário, release estável oficial, SHA256 do arquivo/binário e publicação atômica; OpenJarvis já fixado; pesos com digest registrado | Download real do Ollama e dos modelos, inferência Local real sem internet, CLI e GUI |
| Perfis | GUI prepara o novo serviço antes de substituir a sessão ociosa; preserva autorizações; falha de preparação/gravação mantém o perfil anterior | Alternância com ambos os provedores reais disponíveis |
| Desempenho | Comparador com 3 rodadas descarregadas e 30 aquecidas por cenário/modelo, RAM da árvore e PID do Ollama, negações/números, detecção de efeitos extras/duplicados | Dois modelos reais, revisão de qualidade e escolha por p95/PSS; otimização residente condicionada à medição |
| Engenharia | Ferramentas `project_checkpoint` e `project_service`, SQLite, PID/starttime/boot ID, health de loopback vinculado ao socket do processo; revalidação antes da retomada | Jornada FCC real de clonar, instalar dependência em cache, configurar, testar, iniciar e retomar projeto |
| STT | Uso somente de cache durante a conversa; preparação explícita; avaliador de corpus consentido existente | Amostras humanas de 3/10/25/60 s, pausa de 800 ms, números/negações e Bluetooth |
| TTS | Benchmark real de Piper/Kokoro para WAV, carga fria/aquecida e RSS/PSS; Piper real medido | Dependências/pesos Kokoro, síntese e Parar reais; inteligibilidade e reprodução Bluetooth |
| Captura/ativação | Trava entre processos; distribuição dos mesmos quadros normalizados em filas limitadas; palma opcional, debounce de 1,5 s, um pedido e solicitação de exibição da GUI | Palmas/negativos acústicos; Jarvis isolado ≥18/20 e ≤1 falso em 30 min; o fallback STT segue identificado |
| Doctor/lançador | JSON compatível, apresentação humana e na GUI; testes ativos explícitos com timeout; lease e IPC Unix por usuário/sessão, socket 0600 e UID do par | Foco GNOME/Wayland, 30 turnos físicos offline; Windows somente após Linux |

## Preparação no terminal com rede e sessão normal

Nenhum comando de inicialização baixa modelos. O provisionador de arquivo
`.tar.zst` do Ollama exige Python 3.14+; a execução do aplicativo continua com
Python 3.10+. Use a venv do aplicativo e instale os extras necessários previamente.

```bash
jarvis-fcc local install-engine
jarvis-fcc local install-ollama
jarvis-fcc local install-stt --model small
jarvis-fcc local serve
```

`serve` permanece em primeiro plano até Ctrl+C. Solicita CPU, um modelo carregado,
uma inferência paralela e `OLLAMA_NO_CLOUD=1`; usa o diretório gerenciado próprio.
O worker também solicita `num_gpu=0`. Outro daemon não recebe essas configurações
retroativamente. Em outro terminal, baixe os candidatos escolhidos explicitamente:

```bash
jarvis-fcc local pull-model gemma4:e2b
jarvis-fcc local pull-model qwen3:0.6b
jarvis-fcc --profile local --doctor --doctor-format human
jarvis-fcc --profile local --doctor --active-test inference
jarvis-fcc --profile local --gui
```

Os nomes são candidatos para avaliação, sem recomendação de qualidade ou mudança
de padrão. `model-pins.json` registra os digests observados após o pull; não é um
bloqueio contra um administrador trocar pesos externamente. O comparador registra
novamente a identidade efetiva usada. OpenJarvis precisa estar preparado antes
do registro dos digests. Na GUI, informe o modelo de destino em Modelos e aplique
perfil/modelo. Variáveis explícitas `JARVIS_PROFILE`, `FCC_MODEL` e
`JARVIS_LOCAL_MODEL` prevalecem sobre a seleção salva.

## Doctor e reprodução

`--doctor` continua retornando JSON por padrão, sem sockets, modelos carregados,
inferência, microfone ou reprodução. Configurações → Diagnósticos oferece a
apresentação humana. Presença de arquivo não é integridade nem funcionamento.
Os testes ativos são opt-in, em processo separado, com prazo de 1–300 s. Falha de
teste ativo retorna código de saída 1. Segredos vão ao filho por stdin, nunca
por argv ou relatório. Exemplos de ações explícitas:

```bash
jarvis-fcc --doctor --active-test stt --sample /caminho/externo/amostra-consentida.wav
jarvis-fcc --doctor --active-test tts --doctor-output /tmp/voz-nova.wav
jarvis-fcc --doctor --active-test microphone
jarvis-fcc --doctor --active-test playback
```

Microfone captura três segundos e apaga o WAV. STT não persiste a transcrição no
relatório. Playback sintetiza e aciona o player; não confirma que o usuário ouviu.
A trava entre processos impede captura/reprodução concorrente; um teste pode
falhar ou aguardar o dono atual, respeitando o prazo. Mudo/Parar continuam
disponíveis na sessão; não se promete barge-in acústico.

## Comparação e revisão sem repetir inferências

Informe o PID real do daemon gerenciado. São 198 turnos por modelo: seis cenários,
cada um com três amostras frias e trinta aquecidas. Frio significa pesos
descarregados do Ollama; o cache de disco do sistema não é limpo.

```bash
PYTHONPATH=src python -m jarvis.model_comparison \
  --model gemma4:e2b --model qwen3:0.6b --monitor-pid PID_REAL \
  --output /tmp/comparacao.json --review-output /tmp/respostas-para-revisao.jsonl
```

O relatório de métricas não contém pedidos/respostas. O arquivo opcional de
revisão contém apenas os casos dirigidos do benchmark e suas respostas; é novo,
0600 e deve ficar fora de qualquer Git. Não há gravação de áudio ambiental.
Os casos informativos exigem revisão humana de qualidade; passar ferramentas não
prova qualidade semântica. Após revisar, prepare JSON com `report_sha256` do
relatório exato e `models` com uma entrada por modelo contendo `quality_rate`,
`critical_rate`, `reviewed_turns`, `oom`, `wrong_effects` e `duplicate_effects`.
A taxa crítica deve ser 1, qualidade ≥0,95, contagem de revisão completa e os três
contadores de incidentes iguais a zero. Aplique a revisão sem novas inferências:

```bash
PYTHONPATH=src python -m jarvis.model_comparison --results /tmp/comparacao.json \
  --quality-review /tmp/revisao.json --output /tmp/selecionado.json
```

Somente resultados completos, sem efeitos indevidos e com PSS/daemon presentes
participam. Ordenação: menor pior p95 aquecido entre cenários; empate por pico
PSS. A seleção é uma indicação no relatório e não muda preferências. O relatório
também compara startup do primeiro worker com primeiro texto; mediana acima de
10% indica investigar processo residente. Não foi aplicado esse ajuste sem
medição real. STT/TTS e isolamento externo continuam gates separados.

## Engenharia e retomada

As duas ferramentas entram no registro existente somente para Engenharia FCC;
o perfil Local continua bloqueando processos arbitrários. `project_service`
aceita `start/status/stop`, nome, `cwd`, `argv` e health HTTP de loopback sem
credenciais/query/redirect. Start/stop exigem terminal; start exige também acesso
aos dados da conta. Nenhuma concessão real é adicionada automaticamente.

O serviço é direto, sem shell implícito nem daemonização interna. Pode continuar
após fechar Jarvis até `stop` explícito. Health só é verificado quando a porta
está aberta pelo próprio PID, evitando confundir outro servidor com o efeito.
PID/starttime/boot ID e hash de configuração ficam em SQLite. Há limite de dois
serviços; um início incerto bloqueia repetição automática. Detached daemons e
health servido exclusivamente por um filho exigem observação adicional, sem
declaração de sucesso. Não se encerra um PID cuja identidade mudou.

`project_checkpoint` observa URL sem credenciais, ref/SHA e metadados da `.venv`,
sem executar código do projeto. Aceita revisão e distribuições esperadas. Isso
não substitui instalar dependências ou rodar testes por `execute_process` com
autorização. O planejador persiste esses artefatos e revalida etapas verificadas
antes dos próximos efeitos; alteração suspende a retomada em vez de reinstalar,
clonar ou iniciar serviços silenciosamente.

## Lançador e ativação

Após instalar o pacote, `jarvis-show` ou `python jarvis-show.py` usa a mesma GUI.
Em checkout sem instalação, acrescente `PYTHONPATH=src`. A lease usa flock e IPC
Unix por usuário/sessão gráfica. Outro lançamento envia somente `show`; não
inicia outro backend nem concede ferramentas. O servidor verifica UID e restringe
o socket a 0600. A resposta IPC confirma enfileiramento, não concessão de foco.

Palma é experimental e desativada por padrão. Ative em Voz somente na sessão
preparada. Ela usa o stream existente, exige impulso curto/quietude, tem debounce
de 1,5 s e abre um único pedido. Pausa da escuta, execução e fala do assistente
impedem sua detecção. Não há captura para detectar palmas quando o aplicativo
está fechado. Os testes sintéticos de impulso/tom/ruído não comprovam desempenho
acústico com pessoas e Bluetooth.

## Evidência real e limites desta sessão

O Doctor básico foi executado: OpenJarvis/Whisper/Piper/player presentes; Ollama
ausente. O instalador real tentou consultar a release oficial e falhou em DNS,
sem manifestar uma instalação incompleta. Esta sessão também bloqueia sockets
de aplicação fora dos testes autorizados. Não foi alterada a rede nem executado
um ensaio offline físico disfarçado de teste.

Piper real, 30 sínteses da mesma frase dirigida, sink WAV sem reprodução:
SHA256 do modelo `858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7`.
Primeiro WAV frio 6,590 s; 29 aquecidas, primeiro WAV p50/p95 0,221/0,319 s;
duas frases completas p50/p95 0,491/0,647 s. Pico RSS/PSS da árvore
292.992/265.033 KiB. Não mede latência fim de fala, áudio no fone ou Kokoro.
O JSON sanitizado acompanha o checkpoint; arquivos de áudio não são versionados.

Permanecem pendentes os ensaios reais listados na tabela, a fixture completa
com dependência instalada do cache via FCC real e os 30 turnos finais offline.
Sem esses gates não se declara o plano completamente concluído, não se muda
Whisper/Piper/FCC padrão e não se inicia validação Windows.
