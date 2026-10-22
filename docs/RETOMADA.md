# JARVIS — ponto de retomada (21 de outubro de 2026)

## Contexto confirmado pelo usuário (Ubuntu GNOME Wayland)

Projeto: [Bryan9895/free-jarvis](https://github.com/Bryan9895/free-jarvis). A JARVIS roda como CLI Python (`jarvis-fcc`) e conversa com o Free Claude Code (FCC) pela API Responses, em geral em `http://127.0.0.1:8082`. Modelo que funcionou no notebook: `openai/gpt-5.6-luna` (o catálogo pode mudar). O workspace padrão é `~/Projetos`, independentemente do diretório onde o código está clonado. Pastas extras só são acessíveis com `JARVIS_ALLOWED_DIRS`.

**Funcionalidades efetivamente testadas no notebook e confirmadas pelo usuário:** abrir Firefox e VS Code; criar pastas; criar `main.py` com conteúdo solicitado e abrir no VS Code; listagem do GNOME Shell via extensão Window Calls Extended, incluindo Firefox, Nautilus e Ptyxis com título/PID/foco.

**Implementado no código, mas com testes automatizados ou ressalvas:** planejamento supervisionado com SQLite, retomada manual; criar projetos Python; acesso e mudanças dentro de raízes autorizadas; verificação independente de pastas e hash SHA-256 de arquivos gravados; `open_project`, `open_file`, `managed_processes`; descoberta XDG de apps; inventário via GNOME Shell com fallback AT-SPI; comparação de inventários antes/depois da abertura com estados `already_observed`, `appeared_after_request`, `window_changed_after_request`, `observed_unknown_origin`, `not_observed`, `unavailable`.

**Não está concluído ou não foi comprovado:** afirmar qual arquivo está efetivamente ativo no editor; identificar sem ambiguidade qual solicitação causou abertura de nova instância; colocar janela em foco, redimensionar, mover ou fechar janelas; controle gráfico genérico contínuo; escuta por voz contínua; GUI própria. Testes automatizados simulam janelas; correlação antes/depois no GNOME real ainda exige teste do usuário.

## Como reinstalar em outro Ubuntu

Veja **[README — Instalação rápida](../README.md#instalação-rápida-no-ubuntu-gnome-wayland)**. Precisa instalar o FCC **separadamente** e deixar seu serviço ativo; o JARVIS não inclui o servidor, contas ou credenciais. Clonar por HTTPS, criar `.venv`, instalar extras opcionais e configurar `FCC_URL`/pastas. Para inventário de janelas, a extensão [Window Calls Extended](https://extensions.gnome.org/extension/4974/window-calls-extended/) precisa ser instalada/ativada manualmente e ser compatível com a versão do GNOME.

Diagnósticos independentes do modelo: `jarvis-fcc --doctor`, `jarvis-fcc --desktop-info`, `jarvis-fcc --windows-diagnostic`. Diagnósticos do FCC (requerem servidor): `jarvis-fcc --health`, `jarvis-fcc --models`, `jarvis-fcc --check-fcc`. Testes: `PYTHONPATH=src python -m unittest discover -s tests -v`.

## Avanço de 22/10/2026 — ativação supervisionada de janela

Implementada ferramenta `focus_window(app, title="")` no `src/jarvis/window_focus.py`, usando Window Calls Extended para conferir janelas e a extensão **opcional e separada** [Activate Window By Title](https://extensions.gnome.org/extension/5021/activate-window-by-title/) para solicitar foco via D-Bus. A ferramenta recusa correspondências múltiplas, títulos idênticos, solicita confirmação explícita e só retorna `focused_verified` quando a mesma janela aparece como focada no inventário posterior. Em caso de ausência da extensão, informa `unavailable`. Testes automatizados foram criados; **validação física no Ubuntu do usuário ainda pendente**. Não habilita `Shell.Eval`, ações remotas irrestritas, fechamento ou movimento de janelas.

**Próximo teste no notebook:** instalar/habilitar Activate Window By Title (sem desativar Window Calls Extended), atualizar via `git pull --ff-only origin main` e testar `Jarvis, coloque o Firefox em primeiro plano`, em cenário com uma janela do Firefox e VS Code aberto. Testar também com duas janelas Firefox para verificar `ambiguous`.

## Próximo objetivo ao retomar

**Controle supervisionado de janelas GNOME Wayland** sobre a base já validada: determinar identificador confiável de janela; avaliar métodos permitidos pela extensão e pelo compositor para solicitar foco/seleção **somente com autorização humana**; verificar o resultado pela leitura do GNOME Shell; impedir confusões quando há múltiplas janelas da mesma aplicação. Separar presença de janela de prova de ação concluída. Não utilizar `Shell.Eval`, bypass de Wayland ou comandos shell livres.

Antes de ampliar capacidades, validar em notebook o comparador antes/depois com Firefox fechado e Firefox aberto, e com projeto VS Code já existente, conferindo os estados reportados. Prosseguir então com design de operações por identificador e autorização específica, preservando testes regressivos e histórico SQLite.

## Segurança e operação

Aprovações para mudanças locais continuam obrigatórias. `delete_path` envia para lixeira interna recuperável, não apaga permanentemente. `JARVIS_ENABLE_DESKTOP_INPUT` deve permanecer desativado por padrão. Captura de tela, voz e navegador exigem extras e permissões separadas. **Não** versionar tokens, conteúdo de conversas, banco SQLite, capturas nem segredos do FCC. Não copiar credenciais de um notebook para outro sem decisão do usuário. O nome `jarvis-fcc` evita conflito com pacotes genéricos de nome `jarvis`.

## Entrega seguinte — abertura + foco e redução de espera (22/10/2026)

A ferramenta `focus_window` permanece supervisionada, exigindo Window Calls Extended e Activate Window By Title. Adicionadas `launch_installed_app_and_focus`, `open_project_and_focus` e `open_file_and_focus`, que fazem duas operações e devolvem duas evidências distintas (`launch` e `focus`). Há duas autorizações separadas quando necessárias. Uma janela já focada não gera novo comando de foco; múltiplas janelas de uma aplicação ou títulos duplicados bloqueiam ativação em vez de escolher por sorte.

**Desempenho:** `window_tracking.snapshot()` usa agora somente a extensão GNOME Shell, com prazo de consulta mais curto (1,5s), e não faz mais fallback lento AT-SPI a cada lançamento. Não repete consulta quando GNOME Shell está indisponível. `jarvis-fcc --windows-diagnostic` preserva fallback completo para diagnosticar. Verificar `/metricas` para distinguir demora do FCC (`model_s`) de espera por ferramentas.

**Reparo:** `ProcessManager.open_file` passou a persistir corretamente `window_observation` em `managed_processes` e foi removido código inacessível.

**Validação pendente no computador:** após atualizar (`git pull --ff-only origin main`), confirmar as duas extensões habilitadas; solicitar `Jarvis, abra o Firefox e coloque a janela em primeiro plano`; conferir `launch.status` e `focus.status` (com duas autorizações se necessário). Fazer o mesmo com projeto existente no VS Code; em caso de demora fornecer o JSON do comando `/metricas`. O foco real no desktop continua condicionado à extensão e ao estado observado, não é garantido por testes simulados.

## Incidente FCC/NIM em 22/10/2026 — resolvido no código, testar no computador

Ao perguntar `Jarvis, quais janelas estão abertas no meu computador?`, FCC iniciou com `nvidia_nim/nvidia/nemotron-3-super-120b-a12b`, trocou automaticamente para `nvidia_nim/google/diffusiongemma-26b-a4b-it` e recebeu erro 400 `Empty content is not allowed for assistant messages`. Foi identificado risco de reenvio de mensagens assistant vazias no histórico de resposta de ferramentas. Em `src/jarvis/agent.py` elas são removidas antes da próxima rodada, preservando `function_call` e `function_call_output`. Em `src/jarvis/fcc.py`, pedidos com ferramentas não usam mais fallback implícito indiscriminado do catálogo do provedor; backups explícitos continuam elegíveis. Testes de regressão adicionados. Validar no GNOME/FCC real antes de afirmar que o problema desapareceu.

No notebook: encerrar JARVIS, `cd ~/free-jarvis && git pull --ff-only origin main && source .venv/bin/activate`; consultar `jarvis-fcc --models` e escolher um modelo de function calling previamente funcional (por exemplo `export FCC_MODEL='openai/gpt-5.6-luna'` somente se anunciado), `unset FCC_FALLBACK_MODELS FCC_ALLOW_CROSS_PROVIDER`; executar `jarvis-fcc`, perguntar janelas, depois `/metricas`. Se erro persistir, registrar mensagem de erro, modelo e métricas para separar incompatibilidade de NIM/FCC de erro de ferramenta.

## Plano de foco contraditório observado em 22/10/2026

O usuário apresentou o plano #2 para "coloque a janela do Firefox em primeiro plano", contendo duas etapas redundantes. A primeira alegou ter confirmado foco, mas a segunda alegou não encontrar Firefox, e ambas ficaram "resultado não verificado". Este relatório **não comprova** foco efetivo: o texto foi gerado pelo modelo; o verificador anterior só tratava operações de arquivo/abertura. Corrigidos: classificador trata localizar+focar a mesma janela como ação única; planejador exige resultado concreto de `focus_window` para marcar foco como verificado e para continuar; falha ou falta de chamada para a sequência; apelidos comuns Firefox e VS Code reconhecidos pelo cliente de janela. Testes simulam sucesso, ausência de ferramenta e foco indisponível.

Próximo teste real: atualizar via `git pull --ff-only origin main`, iniciar JARVIS e solicitar **sem pedir planejamento** "Jarvis, coloque a janela do Firefox em primeiro plano"; confirmar autorização explícita e verificar posteriormente usando `jarvis-fcc --windows-diagnostic` em outro terminal ou `/metricas` para conferir se `focus_window` foi chamada. Se o Firefox já tiver foco, `already_focused` é um sucesso de observação sem mudança. Nunca assumir sucesso a partir do texto do modelo apenas.

## JARVIS v0.2.0 — autoaprovação de ações (22/10/2026)

A pedido do usuário, `ApprovalPolicy` foi adicionada em `src/jarvis/approval.py` e integrada à CLI. O usuário pode executar `jarvis-fcc --auto-approve` para consentimento antecipado durante a sessão, ou alternar com `/permissoes auto`, `/permissoes manual` e `/permissoes status`. Eventos ficam visíveis no terminal com `AUTOAUTORIZADO`. A política é encaminhada aos fluxos que já usam `confirm` (toolkit, planos e operações opcionais). O padrão continua manual em novas sessões sem a flag.

Limites intactos: permissões GNOME Wayland de portal, proteção de diretórios `JARVIS_WORKSPACE`/`JARVIS_ALLOWED_DIRS`, comando em allowlist, limitações de ferramentas e validações de efeitos. Não há `sudo`, shell arbitrário ou acesso irrestrito. Essa versão **dispensa confirmações internas**, mas não concede "permissão total do sistema".

Criado `tests/test_approval.py` para modo padrão manual, modo automático, retorno a manual e rejeição de caminhos fora do workspace. Arquivo `pyproject.toml` alterado para versão 0.2.0. Testar diretamente em Ubuntu após `git pull --ff-only origin main`; GitHub Actions pode ficar em fila antes da confirmação. Experimento sugerido: executar com `--auto-approve`, pedir foco Firefox e verificar que não aparece entrada `SIM`; usar `/permissoes status`; alternar manual e verificar que volta a pedir `SIM`.

## JARVIS v0.3.0 — gerenciamento de estado de janela (22/10/2026)

Implementados `window_manage.py`, ferramenta `manage_window(app,action,title?)` para minimizar (`minimize`), restaurar (`restore`), maximizar (`maximize`) e desfazer maximização (`unmaximize`). A extensão preexistente **Window Calls Extended** expõe apenas inventário/foco e não implementa tais operações. Foi escolhida a extensão **Window Control** do projeto https://github.com/carlo9890/gnome-window-control (GNOME 45–50) com interface D-Bus `org.gnome.Shell.Extensions.WindowControl.ListDetailed` e operações com ID numérico, estado detalhado `is_minimized`/`is_maximized`.

A dependência de Window Control é **opcional e não instalada automaticamente**, página: https://extensions.gnome.org/extension/10886/window-control/ . Quando ausente, `manage_window` retorna `unavailable` indicando o link. O usuário deve instalá-la e habilitá-la conscientemente; sua interface D-Bus não possui ACL, então outros processos na mesma sessão também podem invocá-la. Fluxo: inventário detalhado → identificação única por classe/título → aprovação normal ou autoaprovação da sessão → nova identificação de ID/título/classe/PID → chamada D-Bus permitida → releitura para verificar estado final. Não são usados Shell.Eval nem X11 nem comandos arbitrários. Resposta direta do agente após chamada única evita segunda inferência. Roteador seleciona apenas `manage_window` em pedidos não compostos.

Testes em `tests/test_window_manage.py` cobrem ambiguidades, alterações de identidade, recusa, ausência de extensão, confirmação/no-op, parse e resposta direta. Versão do pyproject incrementada para `0.3.0`. Precisa validação real no Ubuntu após instalar Window Control e atualizar código. Exemplo: `jarvis-fcc --auto-approve` seguido de "Jarvis, maximize a janela do Firefox" e `/metricas`. Limites da v0.3.0: não permite mover/redimensionar/fechar janelas. Sem extensões ativas retorna indisponível, não contorna Wayland.

## v0.4.0 — correção Firefox minimizado/maximizado + layout lado a lado (22/10/2026)

No Ubuntu real, usuário confirmou `minimize` Firefox com `state_verified`, mas ao solicitar `maximize` depois, JARVIS retornou `already_in_state` enquanto o Firefox permanecia oculto. Causa: Window Control/GNOME mantém `is_maximized=true` mesmo quando `is_minimized=true`. `src/jarvis/window_manage.py` foi corrigido: para `maximize` e `restore`, se minimizada, executa `Unminimize` e `Activate`, só maximiza adicionalmente quando preciso, e só confirma sucesso após observar `is_minimized=false` além da bandeira `is_maximized`. `tests/test_window_manage.py` cobre estado simultâneo, interrupção e alias terminal.

O nome genérico "terminal" agora corresponde a classes como `org.gnome.Ptyxis`, mas se houver duas janelas Ptyxis a resposta será `ambiguous` sem escolher uma janela por acaso. Informe título parcial único.

Nova funcionalidade em `src/jarvis/window_layout.py`: `place_window(app,position,title?)` e `arrange_windows(left_app,right_app,left_title?,right_title?)`, com seleção única do inventário `Window Control.ListDetailed`, área útil obtida por `GetWorkarea`, `MoveResize`, restauração/desmaximização quando necessárias, revalidação dos IDs e conferência aproximada de geometria. Resposta única determinística após `geometry_verified`/`layout_verified`, sem rodada extra FCC. Ações parciais não são declaradas concluídas. Referência https://github.com/carlo9890/gnome-window-control . Não instalar extensão automaticamente; requer a já usada `window-control@carlo9890.github.io`.

Comandos teste após atualizar e `jarvis-fcc --auto-approve`: "Jarvis, minimize o Firefox", "Jarvis, maximize o Firefox" (deve reaparecer), "Jarvis, coloque o Firefox na metade direita da tela", "Jarvis, coloque o Firefox e o VS Code lado a lado" (VS Code deve estar aberto). Depois `/metricas`. Ainda é preciso validar fisicamente o layout no notebook. A versão do pacote foi elevada a 0.4.0. Confirmação final do CI deve ser verificada antes de afirmar que todos os testes passaram.

## v0.5.0 em andamento — primeira entrega de controle avançado

O novo roadmap prioriza gerenciamento completo de janelas antes da arquitetura modular. Nesta entrega, `place_window` ganhou `center`, `bottom_right` e percentuais de largura/altura da área útil; `focused_window` confronta `GetFocused` com `ListDetailed`; `close_window` usa o ID revalidado e só confirma fechamento após desaparecer do inventário. Fechamento exige aprovação manual específica mesmo em sessão `--auto-approve`, pois documentos não salvos podem abrir um diálogo. Foram adicionados testes simulados; não há confirmação física no Ubuntu ainda. O pacote permanece v0.4.0 enquanto os demais critérios de v0.5.0 estiverem abertos.

Próximo teste no notebook: com Window Control habilitado e janela descartável, pedir centralização, canto inferior direito, tamanho de 70% e consulta de foco; depois fechar a janela e conferir `closed_verified`. Repetir com duas janelas do mesmo aplicativo para confirmar `ambiguous`. Conferir `/metricas` e a geometria visualmente. O fechamento pode retornar `close_unverified` enquanto houver diálogo de salvamento; não repetir automaticamente.

## v0.5.0 — grade e perfis locais de janelas

Adicionadas `arrange_window_grid` (três janelas: esquerda + duas à direita; quatro: 2×2) e `save_window_layout`, `list_window_layouts`, `restore_window_layout`. Perfis ficam em tabela própria do SQLite de `JARVIS_DB`, guardando classes/títulos e geometria relativa à área útil. Restauração redimensiona para a área atual e exige que as janelas ainda estejam abertas, inequívocas e no mesmo monitor. Todas as ações de movimento revalidam identidade e medem o resultado; não há declaração de sucesso para aplicação parcial. Testes são simulados; **validação física continua pendente**. Não elevar `pyproject.toml` a v0.5.0 até cumprir os critérios de aceite e testar no Ubuntu.

## Próxima entrega local da v0.5.0 — pixels e histórico

`place_window(position="custom")` recebe `x_px`, `y_px`, `width_px`, `height_px` relativos à área útil do monitor e recusa coordenadas fora dela. A trilha `window_action_history` registra ferramenta, status, aplicativo e geometria sanitizada em tabela própria de `JARVIS_DB`; títulos de janelas não são gravados. Testes automatizados foram adicionados. O teste real de posicionamento por pixels no Ubuntu e a conferência do histórico após ações reais ainda precisam ser feitos pelo usuário.

No ambiente de desenvolvimento desta entrega, `jarvis-fcc --desktop-info` confirmou sessão Ubuntu GNOME Wayland e portais de captura/RemoteDesktop disponíveis. A extensão Window Control respondeu a `GetVersion` com `('4',)` e a `GetCapabilities` com `rules`, `rules-title-affix`, `keybindings`, `no-animation` e `activate-no-animation`. Essas consultas são somente leitura; não comprovam que `MoveResize` tenha aplicado a geometria de uma janela real.

## Validação real da v0.5.0 com janelas descartáveis (22/10/2026)

No GNOME Wayland ativo, XTerm descartável confirmou `geometry_verified` para centro e pixels, `focused_verified` para consulta de foco e `closed_verified` para fechamento. Três e quatro XTerm foram organizados em grade com `layout_verified`; perfil salvo, janela movida e perfil restaurado também retornaram `layout_verified`. Seleção de várias XTerm sem título retornou `ambiguous`. A trilha SQLite registrou as ações sem título de janela.

O teste descobriu que `GetFocused` do `gdbus` traz `uint64` textual, corrigido no parser. Também mostrou que `MoveResize` redimensiona XTerm sem mover; `Move` separado aplica a posição. A verificação final permanece obrigatória. Uma janela GNOME Calculator recusou a altura pedida por limite do aplicativo e manteve `geometry_unverified`, sem falso sucesso.

Próximo passo: validar aplicativos cotidianos e monitor adicional quando disponível; depois iniciar v0.6.0 com inventário de monitores e áreas de trabalho. Não marcar v0.5.0 como lançada antes dos critérios restantes.

## v0.6.0 — primeiro passo: inventário GNOME somente leitura

`desktop_spaces` foi integrado ao agente e roteador para listar monitores e áreas de trabalho por Window Control, sem modificar o desktop. A resposta D-Bus é limitada e validada; áreas úteis são incluídas somente quando cabem no monitor correspondente. No Ubuntu real, a ferramenta retornou monitor 0 de 1366×768, área útil `(53, 32, 1313, 736)` e áreas 0 (ativa) e 1 (inativa). O teste automatizado inclui dois monitores simulados, dados inválidos e roteamento de pedidos. A alternância e o movimento entre áreas foram implementados na etapa seguinte; testar monitor adicional quando disponível.

## v0.6.0 — alternância e movimento entre áreas verificados

`activate_workspace` e `move_window_to_workspace` usam números humanos começando em 1, exigem área existente, autorização, revalidação após a autorização e leitura posterior do compositor. A segunda ferramenta recusa janela ambígua ou fixa em todas as áreas. No GNOME Wayland real, uma XTerm descartável foi movida da primeira para a segunda área, a segunda foi ativada, a primeira reativada e a XTerm devolvida; as quatro operações retornaram estados verificados. A área originalmente ativa foi restaurada e a janela descartável encerrada. Histórico SQLite registrou quatro ações sem título. O movimento entre monitores está descrito abaixo; perfis completos de ambiente ainda faltam e um monitor adicional não estava disponível para teste físico.

## v0.6.0 — movimento de janela entre monitores implementado

`move_window_to_monitor` seleciona um monitor por número humano ou o único outro monitor conectado. Revalida topologia e janela após autorização, solicita `MoveToMonitor` e exige que `ListDetailed.monitor_index` confirme o destino. Com um monitor real, XTerm descartável retornou `not_found` para outro monitor e `already_in_state` para o monitor atual; nenhuma janela foi movida. Testes com dois e três monitores simulados cobrem sucesso, ambiguidade, recusa, mudança da disposição e comando enviado sem movimento observado. O teste físico de mudança entre monitores aguarda um segundo monitor conectado. Próximo item: perfis completos de ambientes de trabalho.
