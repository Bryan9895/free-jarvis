# Interface Jarvis — análise e plano

Referência analisada em 23/10/2026: FatihMakes/Mark-LVI, main `4d4035c1b40a3bc796ac63f2f1b6a99bc0dd334d`.

## Estrutura da referência

Inventário completo da árvore consultado; leitura representativa de README, licença, ui.py, main.py, dashboard/server.py, providers/registry.py e core/wake_word.py. Isso é análise de arquitetura, não auditoria de cada linha de todas as ações.

| Grupo | Papel na referência | Equivalente no free-jarvis |
|---|---|---|
| main.py | Orquestração e inicialização | cli.py, service.py, agent.py |
| ui.py | PyQt6: HUD, chat, painéis e overlays | gui.py + novos gui_shell.py/gui_theme.py |
| actions/ | Operações de computador, navegador, arquivos e serviços | Toolkit, ferramentas e adaptadores GNOME |
| providers/ | Contratos e registro de LLM/STT/TTS/engine | providers.py, FCC, VoiceIO |
| core/ | Áudio, wake word, confirmação, avatar, plugins, resultados | voice.py, approval.py, registry.py, execution_result.py |
| memory/ | Configuração e memória persistente | Config e SQLite |
| dashboard/ | Interface HTTP/móvel e pareamento | Fora do escopo desta entrega desktop |
| plugins/ | Extensões | Registro explícito de plugins existente |

A UI possui header, lateral de estado, HUD/área central, conversa e drawers de controles. A implementação é concentrada em ui.py (~317 KB). Há carregamento tardio de recursos. A documentação de dashboard e seu código divergem sobre TLS padrão; não assumir comportamento por README isolado.

A referência declara CC BY-NC 4.0. Esta entrega usa organização visual como referência, com código novo e identidade própria; não importa código, avatar, logo, fontes nem assets do Mark-LVI. Link de referência: https://github.com/FatihMakes/Mark-LVI.

## Modelo visual

Janela desktop em português: navegação à esquerda, conversa no centro, área de operações à direita. Fundo azul quase preto, ciano para ações/estados ativos, texto claro e contraste legível. HUD vetorial leve mostra estado real: conectando, pronto, escutando, processando, resposta ou erro. Não exibir CPU/RAM/ondas de microfone fictícias.

A navegação substitui a linha longa de abas que não cabia na tela. Áreas: plano, tarefas pessoais, navegador gerenciado, janelas, permissões, ambientes, histórico, métricas e voz. Chat, cancelamento e indicador de microfone ficam sempre visíveis.

## Arquitetura e ordem de implementação

1. gui_theme.py: cores e estilos ttk, sem dependências extras.
2. gui_shell.py: navegação reutilizável e HUD Canvas; sem FCC, banco ou ferramentas.
3. gui.py: manter GuiBackend/filas e integrar a nova estrutura. Chamadas continuam via JarvisService/Toolkit; sem lógica de execução nos widgets.
4. Voz: iniciar automaticamente depois da conexão, salvo --text-only; estado do microfone permanece visível e pode ser desligado. Sem bloquear renderização.
5. Testes: backend existente, navegação e renderização em display virtual quando disponível, regressões de voz. Validar 1366x768 e janela menor.
6. Publicar main conforme autorização permanente do usuário, mantendo CLI compatível.

## Critérios e limites

Manter todas as funções anteriores, cancelar pelo mesmo token e preservar confirmações. Elementos decorativos não provam execução. Interface não fornece interrupção de TTS por voz nem controle de abas Firefox pessoal. Sem servidor web, sem Electron, sem download de assets em execução.

Próximas etapas após esta entrega: extrair cada painel de gui.py, preferências persistentes de UI/áudio, histórico em cartões e estados de progresso mais detalhados. Validar ergonomia com usuário e custo real de CPU/RAM no notebook antes de ampliar animações.
