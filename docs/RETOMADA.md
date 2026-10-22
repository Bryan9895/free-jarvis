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
