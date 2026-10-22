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
