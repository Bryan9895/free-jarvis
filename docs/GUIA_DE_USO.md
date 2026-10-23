# Uso, diagnóstico e recuperação

## Sessão e capacidades

Use `jarvis-fcc` para CLI, `jarvis-fcc --gui` para GUI ou `jarvis-fcc --voice` para gravação de seis segundos por Enter. A GUI mostra conversa, plano, histórico, métricas, modelo, perfis e capacidades. O modo manual apresenta uma pergunta por operação; o modo automático é padrão e aceita ações já permitidas, sem pedir `SIM` repetidamente. Fechar uma janela mantém uma confirmação pontual porque o aplicativo pode ter alterações não salvas. A revogação bloqueia novas ferramentas e cancela novas etapas; uma chamada já enviada ao FCC, navegador ou GNOME pode continuar até retornar. A CLI oferece `/permissoes status|auto|manual|revogar`, `/metricas`, `/plano`, `/retomar-plano` e `/resolver-etapa skip|retry`.

A aba **Voz** mantém o botão de gravação curta para transcrição revisável e também permite ativar **escuta contínua** uma vez por sessão. Nesse modo, a detecção de fala e a transcrição Whisper base rodam localmente; só uma fala cuja transcrição começa com “Jarvis”, “Jarves” ou “Hey Jarvis” inicia uma tarefa. Algumas variantes fonéticas comuns do reconhecimento também são aceitas. O pedido é enviado automaticamente ao mesmo serviço da conversa por texto. Depois da resposta falada, Jarvis continua a conversa por até 20 segundos sem repetir a palavra-chave; após esse período volta a aguardá-la. Diga “Jarvis, parar conversa” para voltar imediatamente ao modo de espera. O áudio é mantido temporariamente em memória e em um WAV removido ao terminar a transcrição; somente o texto de um pedido ativado é enviado ao FCC. A escuta contínua consome CPU enquanto estiver ligada e para ao fechar a GUI ou clicar em **Parar escuta contínua**. `JARVIS_WAKE_MODEL` pode selecionar outro tamanho de Whisper; `base` é o padrão da GUI e o reconhecimento push-to-talk continua usando `JARVIS_WHISPER_MODEL` (padrão `tiny`).

Instale reconhecimento e síntese com `python -m pip install -e '.[voice]'`. A primeira transcrição contínua baixa o modelo Whisper base se ainda não estiver no cache. Baixe uma voz com `python -m piper.download_voices --download-dir ~/.local/share/jarvis/voices pt_BR-faber-medium` e defina `JARVIS_PIPER_MODEL=~/.local/share/jarvis/voices/pt_BR-faber-medium.onnx`. A voz faber pt-BR usa modelo CC0. Falta de microfone ou de pacotes de voz não afeta o modo texto.

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

Na GUI, **Listar microfones** não escolhe mais o primeiro item automaticamente: o campo vazio mantém a entrada padrão/configurada. Ao escolher um item, o nome é usado na captura, evitando índices antigos após reconexão. A gravação curta respeita `JARVIS_WHISPER_MODEL` e `JARVIS_LANGUAGE`, como a CLI.

Uma falha de transcrição na escuta contínua descarta o WAV e retorna ao modo de espera por “Jarvis”, sem enviar a fala ao FCC. Se nenhum quadro de áudio chegar por três segundos, a escuta para com diagnóstico; reconecte/selecione a entrada e reative a escuta. Isso não limita o tempo de carregamento/inferência do Whisper nem chamadas bloqueadas do próprio driver.

## Tarefas, abas e janelas

A GUI (`jarvis-fcc --gui`) inclui **Minhas tarefas**, **Abas gerenciadas** e **Janelas**. O painel de planos continua separado da lista pessoal. O serviço ainda exige conexão inicial com FCC, inclusive para usar os painéis; modo gráfico offline é uma melhoria futura.

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
