# Uso, diagnóstico e recuperação

## Sessão e capacidades

Use `jarvis-fcc` para CLI, `jarvis-fcc --gui` para GUI ou `jarvis-fcc --voice` para conversa contínua (`--push-to-talk` para gravação por Enter). A GUI mostra conversa, plano, histórico, métricas, modelo, perfis e capacidades. O modo manual apresenta uma pergunta por operação; o modo automático é padrão e aceita ações já permitidas, sem pedir `SIM` repetidamente. Fechar uma janela mantém uma confirmação pontual porque o aplicativo pode ter alterações não salvas. A revogação bloqueia novas ferramentas e cancela novas etapas; uma chamada já enviada ao FCC, navegador ou GNOME pode continuar até retornar. A CLI oferece `/permissoes status|auto|manual|revogar`, `/metricas`, `/plano`, `/retomar-plano` e `/resolver-etapa skip|retry`.

A tela inicial mostra conversa e controles. Abra **Configurações → Voz**, com **Conversar**, **Microfone**, **Diagnóstico** e **Saída**. O botão **Falar / terminar** ouve até um segundo de silêncio (configurável); outro clique termina manualmente. **Cancelar pedido** descarta captura e resposta atrasada e interrompe a reprodução. Somente o diagnóstico mantém gravação fixa de seis segundos. Em contínuo, comece com “Jarvis” e continue sem repetir a chamada durante a janela de seguimento de 20 segundos, que não corta fala iniciada. A ativação ainda é fallback por Whisper/regex: **detector acústico de Jarvis isolado não está entregue nem aceito fisicamente**. Captura fica protegida durante resposta; barge-in não é anunciado.

Whisper é local CPU int8, com padrão `small` na GUI e CLI, um único cache compartilhado com diagnóstico e carregamento tardio. Silero local decide atividade de fala; RMS mede nível. Taxa/canais são negociados e o áudio é normalizado uma vez para 16 kHz. O primeiro uso de Whisper pode baixar o modelo. Em Saída, salve STT, entrada, modo, silêncio e limiar VAD; Salvar aplica entrada/STT à sessão ativa; Aplicar em Conversar também permite iniciar a escuta. Metas de precisão e latência não são garantidas por existir o VAD.

**Modelos**, no menu lateral, escolhe a IA de conversa no FCC. Filtre por nome/provedor, escolha no campo abaixo e clique **Usar modelo**. O cabeçalho mostra o modelo realmente ativo; editar a seleção não troca o modelo até confirmar. Se aparecer **HTTP 404 em /v1/responses**, o provedor/modelo pode estar indisponível mesmo listado no catálogo. Na captura fornecida pelo usuário, NIM retornou função não encontrada para a conta: troque o modelo, por exemplo para `openai/gpt-5.6-luna` se constar no catálogo, e repita o pedido. Os detalhes técnicos ficam no painel Modelos. Nenhum modelo alternativo é escolhido automaticamente.


Instale reconhecimento e síntese com `python -m pip install -e '.[voice]'`. Em **Voz → Saída**, clique **Instalar Faber pt-BR (~63 MB)** ou escolha um `.onnx` local acompanhado de `.onnx.json`. O instalador usa revisão fixa da fonte Piper, hashes verificados e preserva MODEL_CARD (dataset CC0) e origem. Escolha saída, Salvar e **Testar voz salva**; confirme que ouviu a frase. Nenhum download de voz ocorre ao iniciar. A saída escolhida requer `paplay`; a padrão pode usar `aplay`. Preferências ficam em `~/.config/jarvis-fcc/preferences.json`, sem tokens. Ambiente explícito (`FCC_MODEL`, `JARVIS_WHISPER_MODEL`, `JARVIS_AUDIO_DEVICE`, `JARVIS_AUDIO_OUTPUT`, `JARVIS_PIPER_MODEL`, `JARVIS_SILENCE_MS`, `JARVIS_VAD_THRESHOLD`) tem precedência. Fonte: [Piper Faber](https://huggingface.co/rhasspy/piper-voices/tree/1af0d6b01d3dbe698a426f0c3424650ef77fc131/pt/pt_BR/faber/medium).

As capacidades são verificadas novamente na execução, inclusive em chamadas diretas e no modo automático. O catálogo enviado ao modelo pode ser filtrado, mas não concede acesso. Acesso a outras pastas exige `JARVIS_ALLOWED_DIRS`; links simbólicos e caminhos resolvidos fora das raízes são recusados. GNOME Wayland também exige suporte das extensões e, para captura/entrada, autorização do portal. O navegador usa Chromium headless separado, sem cookies do Firefox pessoal; bloqueia protocolos e destinos locais/reservados. Resolução DNS pode mudar entre verificação e conexão, portanto não use o navegador isolado como fronteira absoluta contra redes privadas.

## Diagnóstico por camada

| Pergunta | Comando |
| --- | --- |
| Pacote e extras disponíveis | `jarvis-fcc --doctor` |
| Servidor FCC alcançável | `jarvis-fcc --health` |
| Modelos anunciados | `jarvis-fcc --models` |
| Modelo responde de fato | `jarvis-fcc --check-fcc` |
| GNOME/portais detectados | `jarvis-fcc --desktop-info` |
| Inventário de janelas | `jarvis-fcc --windows-diagnostic` |
| Testes automáticos | `python -m unittest discover -s tests -q` |

`--health` não comprova inferência, e inferência não comprova ferramenta GNOME. Se a janela desejada não aparecer, verifique as extensões GNOME compatíveis com sua versão; a instalação delas é manual. Se houver várias janelas semelhantes, especifique título ou escolha uma antes de agir. A GUI não deve ser executada sem sessão gráfica; a CLI segue disponível.

## Dados, atualização e falhas

O banco padrão é `~/.local/share/jarvis-fcc/memory.sqlite3`; `JARVIS_DB` altera o caminho. Antes de uma atualização importante, feche o programa e faça cópia do arquivo. A migração SQLite usa `PRAGMA user_version`, mantém tabelas e linhas antigas e cria as novas estruturas ao abrir. Para voltar à versão anterior, restaure a cópia do banco correspondente; não suponha que código antigo entenda o esquema novo.

Uma etapa interrompida ou com efeito incerto não é repetida automaticamente. Inspecione `/plano`, confirme o efeito no sistema e use `/resolver-etapa skip` se já aconteceu ou `/resolver-etapa retry` se é seguro repetir. Depois use `/retomar-plano`. Para falha de navegador, repita o diagnóstico de pacote/Chromium; timeouts encerram o subprocesso para evitar resposta atrasada. Para FCC indisponível, confira URL, token, modelo e servidor; o histórico local continua no banco.

## Validação física pendente

Em Ubuntu GNOME Wayland do usuário: verificar Firefox e VS Code lado a lado com janelas únicas, aplicativo com tamanho mínimo, janela com diálogo de salvamento, restauração parcial de perfil e cancelamento durante tarefa. O movimento real entre dois monitores exige dois monitores conectados. Registrar versão do GNOME, extensões, resoluções, comando, estado antes/depois e resultado; não marcar como validado somente pela suíte ou por simulação.

## Captura de voz e Bluetooth

`JARVIS_AUDIO_DEVICE` seleciona a entrada SoundDevice por nome (prefira um nome inequívoco; índices podem mudar). A escuta contínua herda essa seleção. No backend PulseAudio, `PULSE_SOURCE` pode selecionar a fonte Bluetooth; confirme o nome atual com `pactl list short sources`. Entradas com `.monitor` capturam saída, e `snd_aloop` é virtual.

A captura curta aguarda a duração pedida mais três segundos de tolerância para receber quadros. Se não houver áudio suficiente, informa tempo limite e libera o stream; isso não confirma que o driver sempre responde ao abrir ou fechar. Não aumente sensibilidade antes de ouvir a captura e conferir a fonte.

Se ocorrer `open() got an unexpected keyword argument 'metadata_errors'`, confira `python -m pip show faster-whisper av`. O extra voice restringe PyAV a versões anteriores à 19; para atualizar uma instalação existente, use `python -m pip install -e '.[voice]'` e `python -m pip check`.

### Escolher a entrada sem FCC

Execute `jarvis-fcc --audio-devices` para listar microfones sem iniciar o servidor ou carregar Whisper. Para selecionar um nome inequívoco, use `jarvis-fcc --voice --audio-device 'NOME DA ENTRADA'`; a mesma opção funciona com `--gui`. Se houver nomes duplicados, SoundDevice rejeita a seleção ambígua; não presuma que o primeiro seja o correto. A lista também pode conter monitores e entradas virtuais.

Na GUI, **Listar entradas** não escolhe mais o primeiro item automaticamente: o campo vazio mantém a entrada padrão/configurada. Ao escolher um item, o nome é usado na captura, evitando índices antigos após reconexão. A gravação curta respeita `JARVIS_WHISPER_MODEL` e `JARVIS_LANGUAGE`, como a CLI.

Uma falha de transcrição na escuta contínua descarta o WAV e retorna ao modo de espera por “Jarvis”, sem enviar a fala ao FCC. Se nenhum quadro de áudio chegar por três segundos, a escuta para com diagnóstico; reconecte/selecione a entrada e reative a escuta. Isso não limita o tempo de carregamento/inferência do Whisper nem chamadas bloqueadas do próprio driver.

### Diagnóstico na aba Voz

Abra `jarvis-fcc --gui` e selecione **Configurações → Voz**. Configuração, instalação de voz e diagnóstico usam uma fila local independente e funcionam enquanto o FCC conecta ou está indisponível. Instale o extra `voice` para captura e Whisper.

1. Conecte o fone Bluetooth e confira no Ubuntu se a entrada ativa é o microfone dele. Na camada **Microfone**, clique **Listar entradas**, selecione um nome inequívoco ou mantenha o campo vazio para a entrada padrão/configurada. A lista SoundDevice pode mostrar apenas `pulse`/`default`; nesse caso, a fonte Bluetooth é escolhida pelo sistema ou por `PULSE_SOURCE`, não digitando um nome `bluez_input` como dispositivo SoundDevice.
2. Clique **Verificar**. Isso consulta taxa/canais aceitos, sem comprovar que sua fala está chegando ou confirmar a fonte PipeWire efetiva. Evite `.monitor` e entradas virtuais.
3. Abra **Diagnóstico**, leia a frase exibida e clique **Gravar 6 s**. A barra mostra o nível da amostra ao terminar. O resultado informa sinal muito baixo/silêncio, sinal detectado ou possível saturação. Ruído também produz sinal: ouça a gravação para conferir.
4. Clique **Ouvir amostra** para reproduzir na saída padrão do Ubuntu. Se houver silêncio, confira fonte, volume e mudo antes de alterar o Whisper. A reprodução requer `paplay` (pulseaudio-utils) ou `aplay` (alsa-utils).
5. Clique **Transcrever** com `base`. Compare o texto reconhecido com a frase de referência. Se a gravação estiver clara e o texto ruim, selecione `small` e transcreva novamente a mesma amostra; pode consumir mais memória e tempo. O primeiro uso pode baixar/carregar o modelo.

A similaridade compara palavras, ignorando acentos, maiúsculas e pontuação; não estima a precisão geral nem testa a ativação contínua por palavra-chave. A frase de referência não é enviada ao Whisper. Escolher o modelo no campo Whisper muda o teste. Para conversar com o mesmo modelo e entrada selecionados, abra **Conversar** e clique **Aplicar modelo e microfone**; isso inicia/reinicia a escuta contínua nesta sessão. O estado exibe o modelo ativo. Diga **Jarvis, quanto é dois mais dois?** e aguarde a resposta na conversa. O botão Transcrever apenas diagnostica o áudio e não envia a frase como pedido. Para iniciar sempre com small, use `JARVIS_WAKE_MODEL=small jarvis-fcc --gui`. Configure resposta falada em Saída; sem voz local válida a resposta visual permanece disponível.

A escuta contínua pausa durante cada operação de diagnóstico e retoma depois. As transcrições de teste não viram comandos nem são enviadas ao FCC. Um único WAV temporário fica disponível para comparação, removido ao gravar outra amostra, clicar **Apagar amostra** ou fechar normalmente a GUI. Encerramento forçado do processo pode deixar o arquivo temporário no sistema.

## Tarefas, abas e janelas

A GUI (`jarvis-fcc --gui`) inclui **Minhas tarefas**, **Abas gerenciadas** e **Janelas**. O painel de planos continua separado da lista pessoal. Os painéis de tarefas, abas e janelas ainda exigem conexão inicial com FCC. Os testes locais da aba Voz estão disponíveis mesmo enquanto a conexão FCC está em andamento.

- Tarefas: adicionar título/prioridade (1 baixa, 2 normal, 3 alta), atualizar e marcar pendente/em andamento/concluída. A lista persiste no banco SQLite; marcar concluída é uma decisão do usuário, não evidência de execução de um plano. Capacidades: `tasks.read` e `tasks.write`.
- Abas: abrir URL pública, atualizar lista, selecionar e fechar por ID da sessão. Fechamento exige confirmação específica por possível perda de formulário. Abas abertas pelo usuário no Firefox pessoal não aparecem. IDs não são reutilizados enquanto o processo Chromium estiver vivo; fechar o Jarvis encerra essa sessão.
- Janelas: informar aplicativo para centralizar, posicionar à esquerda/direita, minimizar, maximizar ou restaurar. Para lado a lado, informar também o segundo aplicativo. Seleção ambígua continua recusada; use o chat com título da janela. Requer as extensões GNOME já documentadas.

O Chromium permanece headless por padrão. Para ver sua janela, defina `JARVIS_BROWSER_VISIBLE=1` **antes** de iniciar Jarvis. Exemplo: `JARVIS_BROWSER_VISIBLE=1 jarvis-fcc --gui`. Não há acesso aos cookies/perfil do Firefox. Instale o extra browser e Chromium conforme README antes de usar abas.

Exemplos de pedidos ao modelo (dependem de function calling correto): “Adicione a tarefa revisar o relatório com prioridade alta”, “Liste minhas tarefas”, “Marque a tarefa 3 como concluída”, “Liste as abas do navegador gerenciado”, “Abra uma nova aba em https://example.com”, “Feche a aba 2 do navegador gerenciado”, “Coloque Firefox e VS Code lado a lado”. Use a GUI para executar diretamente quando o modelo não emitir ferramentas estruturadas.

## Conversa contínua no terminal

`jarvis-fcc --voice` agora inicia a escuta por palavra de ativação, sem Enter e sem revisão obrigatória da mensagem. Diga **Jarvis, seguido do pedido**, aguarde a resposta e continue. Após a resposta há uma janela de até 20 segundos para falar sem repetir o nome; depois volta a exigir Jarvis. Dizer somente Jarvis abre essa janela para o pedido seguinte. Diga **Jarvis, sair** ou pressione Ctrl+C para encerrar. O modo antigo de gravação/revisão está em `--push-to-talk`.

Exemplo: `FCC_MODEL='openai/gpt-5.6-luna' JARVIS_WHISPER_MODEL=small JARVIS_LANGUAGE=pt PULSE_SOURCE='bluez_input.41:42:FF:87:2B:E1' jarvis-fcc --voice`. Confirme o nome da fonte a cada reconexão. Configure a voz pela GUI ou por `JARVIS_PIPER_MODEL`; sem Piper a saída permanece em texto.

A ativação usa transcrição local Whisper e depende da precisão acústica. Não é garantia de reconhecer toda chamada. A escuta fica pausada durante execução/FCC/TTS para não captar a própria resposta; interrupção por voz enquanto fala ainda não é suportada. Confirmações específicas de ações sensíveis e permissões nativas continuam podendo exigir interação. Falha fatal de captura encerra o modo de voz com diagnóstico, em vez de esperar indefinidamente.

## Texto e voz juntos por padrão

Ao iniciar `jarvis-fcc` sem flags, o terminal aceita texto e respeita o modo de voz salvo (continuous, manual ou muted). Não é necessário `--voice` nem Enter para iniciar gravação. Comandos digitados como `/modelos` continuam disponíveis. Sem dependências ou dispositivo de áudio, a escuta informa o erro e o texto permanece disponível. `jarvis-fcc --text-only` não inicia o microfone; `--push-to-talk` mantém o fluxo antigo. `--voice` permanece aceito por compatibilidade, usando o modo misto.

A leitura do teclado e as confirmações ficam na thread principal. Pedidos de voz são enfileirados e processados pelo mesmo serviço; não executam ferramentas em paralelo. A captura pausa ao processar um pedido e durante a resposta para reduzir eco. Para encerrar por voz, diga Jarvis, sair; pelo teclado, digite sair ou use Ctrl+C. O aplicativo precisa estar aberto e o microfone conectado; não é um serviço iniciado automaticamente ao ligar o computador.

## Central gráfica inspirada no Mark-LVI

Inicie com `jarvis-fcc --gui`. Configurações revela a navegação e os painéis de operações, recolhidos no início, mantendo a conversa visível. O tema escuro e o HUD vetorial usam código próprio, sem assets da referência. O HUD indica estados recebidos do backend e não é medidor de áudio.

A voz contínua inicia conforme o modo salvo, sem esperar a conexão ao FCC; a execução de pedidos continua dependendo do serviço. Use **Voz: ligada/desligada** para alternar ou `jarvis-fcc --gui --text-only` para não iniciar o microfone. Microfone indisponível não impede mensagens digitadas. Durante um pedido digitado, a escuta é pausada e retomada após a execução.

Análise e plano: `docs/INTERFACE_MARK_PLANO.md`. Modelo visual ilustrativo: `docs/INTERFACE_MODELO.svg`. Requer ambiente gráfico e Tkinter; no Ubuntu, instale python3-tk se sua instalação Python não incluir Tk. A aparência final no GNOME ainda precisa de verificação física.

## Planos e recuperação na interface

No painel **Plano em execução**, informe um objetivo e clique **Criar plano**. Revise as etapas e use **Executar**. O progresso conta somente etapas verificadas; uma resposta do modelo sem comprovação não aumenta esse indicador. **Histórico** lista planos persistidos; selecione um e clique **Selecionar**.

Para plano interrompido, confira os efeitos no computador. **Repetir etapa** ou **Ignorar etapa** exige confirmação específica, mesmo em autoaprovação. Depois use **Retomar** para preparar pendentes e **Executar** para continuar. **Cancelar plano** cancela o plano parado/pronto; **Cancelar pedido**, abaixo da conversa, sinaliza interrupção do trabalho ativo. Chamadas já enviadas podem terminar e não são desfeitas.

O backend aceita um pedido operacional por vez. Cliques/Enter repetidos não enfileiram execuções silenciosamente; a mensagem digitada permanece no campo se o envio for recusado. Reconectar relê o catálogo do FCC mesmo após uma conexão anterior, mantendo o modelo e o navegador gerenciado. Isso verifica acesso ao catálogo, não inferência do modelo.

A janela compacta de 1040×640 foi renderizada e testada em Xvfb (telas de teste de 1366×768). Capturas de `docs/screenshots/` usam dados de demonstração e backend simulado; não provam integração com GNOME/FCC/microfone reais. Os painéis não selecionados agora são removidos do layout e não forçam tamanho mínimo dos demais.
