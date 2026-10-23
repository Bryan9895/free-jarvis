# Uso, diagnóstico e recuperação

## Sessão e capacidades

Use `jarvis-fcc` para CLI, `jarvis-fcc --gui` para GUI ou `jarvis-fcc --voice` para conversa contínua (`--push-to-talk` para gravação por Enter). A GUI mostra conversa, plano, histórico, métricas, modelo, perfis e capacidades. O modo manual apresenta uma pergunta por operação; o modo automático é padrão e aceita ações já permitidas, sem pedir `SIM` repetidamente. Fechar uma janela mantém uma confirmação pontual porque o aplicativo pode ter alterações não salvas. A revogação bloqueia novas ferramentas e cancela novas etapas; uma chamada já enviada ao FCC, navegador ou GNOME pode continuar até retornar. A CLI oferece `/permissoes status|auto|manual|revogar`, `/metricas`, `/plano`, `/retomar-plano` e `/resolver-etapa skip|retry`.

A aba **Voz** tem três camadas: **Conversar**, **Microfone** e **Testar áudio**. Em **Conversar**, use **Ativar escuta contínua** e comece o pedido com “Jarvis”, “Jarves” ou “Hey Jarvis”. Após uma resposta, a conversa continua por até 20 segundos sem repetir a palavra-chave; diga “Jarvis, parar conversa” para voltar à espera. Ou clique **Apertar para falar · 6 s**, fale durante a gravação e aguarde: a transcrição é enviada automaticamente, sem palavra-chave nem botão Enviar. O atalho **Falar 6 s** fica ao lado do campo de mensagem. A captura contínua pausa durante operações e respostas para evitar eco; não há interrupção da resposta por voz.

Whisper é local, com `small` como padrão da GUI por ter funcionado melhor no teste do usuário. `JARVIS_WAKE_MODEL` altera o modelo inicial da escuta; a CLI mantém seus próprios padrões. A busca de transcrição usa beam size 5 e desativa contexto de transcrições anteriores. Isso não garante precisão e pode aumentar o tempo na CPU. O primeiro uso pode baixar o modelo. O modelo selecionado nas camadas de voz é compartilhado entre teste, aplicação à escuta e gravação pelo botão; mudanças valem nesta sessão. Reconhecimento e TTS são opcionais, sem impedir texto quando indisponíveis.

**Modelos**, no menu lateral, escolhe a IA de conversa no FCC. Filtre por nome/provedor, escolha no campo abaixo e clique **Usar modelo**. O cabeçalho mostra o modelo realmente ativo; editar a seleção não troca o modelo até confirmar. Se aparecer **HTTP 404 em /v1/responses**, o provedor/modelo pode estar indisponível mesmo listado no catálogo. Na captura fornecida pelo usuário, NIM retornou função não encontrada para a conta: troque o modelo, por exemplo para `openai/gpt-5.6-luna` se constar no catálogo, e repita o pedido. Os detalhes técnicos ficam no painel Modelos. Nenhum modelo alternativo é escolhido automaticamente.


Instale reconhecimento e síntese com `python -m pip install -e '.[voice]'`. A primeira transcrição contínua baixa o modelo Whisper selecionado se ainda não estiver no cache. Baixe uma voz com `python -m piper.download_voices --download-dir ~/.local/share/jarvis/voices pt_BR-faber-medium` e defina `JARVIS_PIPER_MODEL=~/.local/share/jarvis/voices/pt_BR-faber-medium.onnx`. A voz faber pt-BR usa modelo CC0. Falta de microfone ou de pacotes de voz não afeta o modo texto.

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

Abra `jarvis-fcc --gui` e selecione **Voz**. Os testes funcionam mesmo após falha da conexão inicial ao FCC; a tentativa inicial de conexão ainda precisa terminar. Instale o extra `voice` para captura e Whisper.

1. Conecte o fone Bluetooth e confira no Ubuntu se a entrada ativa é o microfone dele. Na camada **Microfone**, clique **Listar entradas**, selecione um nome inequívoco ou mantenha o campo vazio para a entrada padrão/configurada. A lista SoundDevice pode mostrar apenas `pulse`/`default`; nesse caso, a fonte Bluetooth é escolhida pelo sistema ou por `PULSE_SOURCE`, não digitando um nome `bluez_input` como dispositivo SoundDevice.
2. Clique **Verificar entrada**. Isso verifica disponibilidade e compatibilidade com captura mono a 16 kHz, sem comprovar que sua fala está chegando. Evite `.monitor` e entradas virtuais.
3. Abra **Testar áudio**, leia a frase exibida e clique **Gravar 6 s**. Fale durante os seis segundos; a barra mostra o nível recebido. O resultado informa sinal muito baixo/silêncio, sinal detectado ou possível saturação. Ruído também pode produzir sinal: ouça a gravação para conferir.
4. Clique **Ouvir amostra** para reproduzir na saída padrão do Ubuntu. Se houver silêncio, confira fonte, volume e mudo antes de alterar o Whisper. A reprodução requer `paplay` (pulseaudio-utils) ou `aplay` (alsa-utils).
5. Clique **Transcrever** com `base`. Compare o texto reconhecido com a frase de referência. Se a gravação estiver clara e o texto ruim, selecione `small` e transcreva novamente a mesma amostra; pode consumir mais memória e tempo. O primeiro uso pode baixar/carregar o modelo.

A similaridade compara palavras, ignorando acentos, maiúsculas e pontuação; não estima a precisão geral nem testa a ativação contínua por palavra-chave. A frase de referência não é enviada ao Whisper. Escolher o modelo no campo Whisper muda o teste. Para conversar com o mesmo modelo e entrada selecionados, abra **Conversar** e clique **Aplicar modelo e microfone**; isso inicia/reinicia a escuta contínua nesta sessão. O estado exibe o modelo ativo. Diga **Jarvis, quanto é dois mais dois?** e aguarde a resposta na conversa. O botão Transcrever apenas diagnostica o áudio e não envia a frase como pedido. Para iniciar sempre com small, use `JARVIS_WAKE_MODEL=small jarvis-fcc --gui`. Resposta falada ainda exige `JARVIS_PIPER_MODEL`; sem Piper a resposta aparece em texto.

A escuta contínua pausa durante cada operação de diagnóstico e retoma depois. As transcrições de teste não viram comandos nem são enviadas ao FCC. Um único WAV temporário fica disponível para comparação, removido ao gravar outra amostra, clicar **Apagar amostra** ou fechar normalmente a GUI. Encerramento forçado do processo pode deixar o arquivo temporário no sistema.

## Tarefas, abas e janelas

A GUI (`jarvis-fcc --gui`) inclui **Minhas tarefas**, **Abas gerenciadas** e **Janelas**. O painel de planos continua separado da lista pessoal. Os painéis de tarefas, abas e janelas ainda exigem conexão inicial com FCC. Os testes locais da aba Voz estão disponíveis após a tentativa de conexão, mesmo se ela falhar.

- Tarefas: adicionar título/prioridade (1 baixa, 2 normal, 3 alta), atualizar e marcar pendente/em andamento/concluída. A lista persiste no banco SQLite; marcar concluída é uma decisão do usuário, não evidência de execução de um plano. Capacidades: `tasks.read` e `tasks.write`.
- Abas: abrir URL pública, atualizar lista, selecionar e fechar por ID da sessão. Fechamento exige confirmação específica por possível perda de formulário. Abas abertas pelo usuário no Firefox pessoal não aparecem. IDs não são reutilizados enquanto o processo Chromium estiver vivo; fechar o Jarvis encerra essa sessão.
- Janelas: informar aplicativo para centralizar, posicionar à esquerda/direita, minimizar, maximizar ou restaurar. Para lado a lado, informar também o segundo aplicativo. Seleção ambígua continua recusada; use o chat com título da janela. Requer as extensões GNOME já documentadas.

O Chromium permanece headless por padrão. Para ver sua janela, defina `JARVIS_BROWSER_VISIBLE=1` **antes** de iniciar Jarvis. Exemplo: `JARVIS_BROWSER_VISIBLE=1 jarvis-fcc --gui`. Não há acesso aos cookies/perfil do Firefox. Instale o extra browser e Chromium conforme README antes de usar abas.

Exemplos de pedidos ao modelo (dependem de function calling correto): “Adicione a tarefa revisar o relatório com prioridade alta”, “Liste minhas tarefas”, “Marque a tarefa 3 como concluída”, “Liste as abas do navegador gerenciado”, “Abra uma nova aba em https://example.com”, “Feche a aba 2 do navegador gerenciado”, “Coloque Firefox e VS Code lado a lado”. Use a GUI para executar diretamente quando o modelo não emitir ferramentas estruturadas.

## Conversa contínua no terminal

`jarvis-fcc --voice` agora inicia a escuta por palavra de ativação, sem Enter e sem revisão obrigatória da mensagem. Diga **Jarvis, seguido do pedido**, aguarde a resposta e continue. Após a resposta há uma janela de até 20 segundos para falar sem repetir o nome; depois volta a exigir Jarvis. Dizer somente Jarvis abre essa janela para o pedido seguinte. Diga **Jarvis, sair** ou pressione Ctrl+C para encerrar. O modo antigo de gravação/revisão está em `--push-to-talk`.

Exemplo: `FCC_MODEL='openai/gpt-5.6-luna' JARVIS_WHISPER_MODEL=small JARVIS_LANGUAGE=pt PULSE_SOURCE='bluez_input.41:42:FF:87:2B:E1' jarvis-fcc --voice`. Confirme o nome da fonte a cada reconexão. Configure `JARVIS_PIPER_MODEL` para respostas faladas; sem Piper, a entrada permanece por voz e a saída em texto.

A ativação usa transcrição local Whisper e depende da precisão acústica. Não é garantia de reconhecer toda chamada. A escuta fica pausada durante execução/FCC/TTS para não captar a própria resposta; interrupção por voz enquanto fala ainda não é suportada. Confirmações específicas de ações sensíveis e permissões nativas continuam podendo exigir interação. Falha fatal de captura encerra o modo de voz com diagnóstico, em vez de esperar indefinidamente.

## Texto e voz juntos por padrão

Ao iniciar `jarvis-fcc` sem flags, o terminal agora aceita mensagens digitadas e ativa a escuta por Jarvis. Não é necessário `--voice` nem Enter para iniciar gravação. Comandos digitados como `/modelos` continuam disponíveis. Sem dependências ou dispositivo de áudio, a escuta informa o erro e o texto permanece disponível. `jarvis-fcc --text-only` não inicia o microfone; `--push-to-talk` mantém o fluxo antigo. `--voice` permanece aceito por compatibilidade, usando o modo misto.

A leitura do teclado e as confirmações ficam na thread principal. Pedidos de voz são enfileirados e processados pelo mesmo serviço; não executam ferramentas em paralelo. A captura pausa ao processar um pedido e durante a resposta para reduzir eco. Para encerrar por voz, diga Jarvis, sair; pelo teclado, digite sair ou use Ctrl+C. O aplicativo precisa estar aberto e o microfone conectado; não é um serviço iniciado automaticamente ao ligar o computador.

## Central gráfica inspirada no Mark-LVI

Inicie com `jarvis-fcc --gui`. A navegação lateral seleciona o painel de operações enquanto a conversa permanece visível. O tema escuro e o HUD vetorial usam código próprio, sem assets da referência. O HUD indica estados recebidos do backend e não é medidor de áudio.

A voz contínua inicia automaticamente após conectar ao FCC. Use **Voz: ligada/desligada** para alternar ou `jarvis-fcc --gui --text-only` para não iniciar o microfone. Microfone indisponível não impede mensagens digitadas. Durante um pedido digitado, a escuta é pausada e retomada após a execução.

Análise e plano: `docs/INTERFACE_MARK_PLANO.md`. Modelo visual ilustrativo: `docs/INTERFACE_MODELO.svg`. Requer ambiente gráfico e Tkinter; no Ubuntu, instale python3-tk se sua instalação Python não incluir Tk. A aparência final no GNOME ainda precisa de verificação física.

## Planos e recuperação na interface

No painel **Plano em execução**, informe um objetivo e clique **Criar plano**. Revise as etapas e use **Executar**. O progresso conta somente etapas verificadas; uma resposta do modelo sem comprovação não aumenta esse indicador. **Histórico** lista planos persistidos; selecione um e clique **Selecionar**.

Para plano interrompido, confira os efeitos no computador. **Repetir etapa** ou **Ignorar etapa** exige confirmação específica, mesmo em autoaprovação. Depois use **Retomar** para preparar pendentes e **Executar** para continuar. **Cancelar plano** cancela o plano parado/pronto; **Cancelar pedido**, abaixo da conversa, sinaliza interrupção do trabalho ativo. Chamadas já enviadas podem terminar e não são desfeitas.

O backend aceita um pedido operacional por vez. Cliques/Enter repetidos não enfileiram execuções silenciosamente; a mensagem digitada permanece no campo se o envio for recusado. Reconectar relê o catálogo do FCC mesmo após uma conexão anterior, mantendo o modelo e o navegador gerenciado. Isso verifica acesso ao catálogo, não inferência do modelo.

A janela compacta de 1040×640 foi renderizada e testada em Xvfb (telas de teste de 1366×768). Capturas de `docs/screenshots/` usam dados de demonstração e backend simulado; não provam integração com GNOME/FCC/microfone reais. Os painéis não selecionados agora são removidos do layout e não forçam tamanho mínimo dos demais.
