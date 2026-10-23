# Arquitetura atual e alvo v1.0

O projeto segue uma migração incremental. Os nomes e interfaces existentes continuam disponíveis; os limites abaixo descrevem a organização real nesta branch e os pontos ainda pendentes.

## Fluxo principal

```text
CLI / GUI / voz revisada
          │
          ▼
     JarvisService ─────── tarefa / cancelar / capacidades
          │
          ├── NaturalTaskController ── TaskPlanner ── PlanStore
          │                │                  │
          └────────────── Agent ◄─────────────┘
                           │
                           ├── ModelProvider ── AutoModelClient ── FCCClient
                           └── Toolkit.execute
                                ├── registro + schema + política
                                ├── filesystem_tools.py
                                ├── browser.py → browser_worker.py
                                ├── process_manager.py / apps.py
                                └── desktop_* / window_* / wayland.py
                                      │
                                      └── GNOME Shell / D-Bus / XDG Portal

       Memory / PlanStore / perfis / eventos ── SQLite versionado
```

## Responsabilidades e dependências

| Camada | Módulos atuais | Regra de dependência |
| --- | --- | --- |
| Interfaces | `cli.py`, `gui.py`, `voice.py` | CLI e GUI chamam `JarvisService`; voz só transforma áudio em texto revisável ou texto em áudio local. |
| Aplicação | `service.py`, `agent.py`, `natural_tasks.py`, `task_intent.py`, `planner.py` | Orquestra pedidos, chamadas, cancelamento cooperativo e planos; não importa widgets GUI. |
| Provedor | `providers.py`, `fcc.py` | `ModelProvider` descreve Responses/modelos; `AutoModelClient` e `FCCClient` implementam adaptação FCC e fallback. |
| Registro e política | `registry.py`, `tool_specs.py`, `schema_validation.py`, `approval.py`, `plugins.py` | `Toolkit.execute` revalida esquema e capacidade no ponto de execução; autoaprovação não muda capacidades. |
| Ferramentas | `tools.py`, `filesystem_tools.py`, `process_manager.py`, `apps.py` | `Toolkit` é fachada/registro de executores; `FilesystemTools` fornece operações de arquivo, mantendo métodos públicos herdados. |
| Desktop | `desktop_*.py`, `window_*.py`, `monitor_control.py`, `workspace_control.py`, `wayland.py` | Adaptadores isolam GNOME Shell, D-Bus, acessibilidade e portais; sucesso exige estado observado quando disponível. |
| Navegador | `browser.py`, `browser_worker.py` | Chromium isolado por subprocesso; páginas são conteúdo externo e não recebem privilégios. |
| Persistência | `database.py`, `memory.py`, `plan_store.py`, `layout_profiles.py`, `desktop_profiles.py`, `window_history.py` | Migrações SQLite são versionadas e compartilhadas; eventos não armazenam argumentos de ferramenta. |
| Evidência/telemetria | `execution_result.py`, `verification.py`, `loop_guard.py` | Resultado estruturado separa envio de efeito confirmado; modelos não comprovam execução. |

## O que a arquitetura já garante

- `JarvisService.ask` impede tarefas simultâneas e fornece token cooperativo. Cancelar impede novas etapas/ferramentas após a operação corrente; não interrompe uma conexão HTTP que já está bloqueada nem desfaz efeitos enviados.
- O registro mantém um executor e uma capacidade por ferramenta. A validação de argumentos e a capacidade são verificadas também em chamadas diretas.
- `filesystem_tools.py` contém limites de caminho, rejeição de escapes por link simbólico, escrita atômica, hash anterior e diff. A verificação pós-escrita compara conteúdo por SHA-256.
- Planos persistidos não repetem etapa incerta sem escolha explícita; texto do modelo não conta como evidência.
- Persistência compartilha o mesmo banco SQLite e preserva tabelas legadas durante migração.
- Voz, Chromium, GUI e GNOME são opcionais e carregados quando usados. GUI e CLI usam o mesmo agente e política.

## Limites ainda abertos

- `tools.py` ainda abriga os executores de navegador, desktop e composição de aplicativos; `agent.py` ainda contém montagem de contexto e loop de ferramentas; `cli.py` ainda contém comandos e chat. A extração de `filesystem_tools.py` é o primeiro corte de módulo, e novas extrações devem manter a API atual coberta por regressão.
- `ModelProvider` formaliza a API síncrona Responses, mas não oferece interrupção de transporte. `FCCClient` usa urllib com timeout; o cancelamento atua depois que a resposta retorna.
- Planos são sequenciais e limitados a cinco etapas; as dependências entre etapas são implícitas pela ordem, sem DAG explícito.
- A GUI possui conversa, tarefas, aprovação, capacidades, ambientes, histórico, métricas e voz; resta validar tarefas e cancelamento longos pela interface real.
- O navegador bloqueia destinos privados/reservados por resolução e rota, mas não oferece isolamento de rede contra DNS rebinding.
- Dois monitores, diálogos de salvamento, Firefox/VS Code no fluxo completo e microfone não foram validados fisicamente nesta entrega local.
