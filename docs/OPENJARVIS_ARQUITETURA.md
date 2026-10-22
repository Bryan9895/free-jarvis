# Estudo de arquitetura: OpenJarvis → JARVIS (22/10/2026)

Referência estudada: https://github.com/open-jarvis/OpenJarvis (ramo `main`). Esta análise usa `README.md`, `pyproject.toml`, `src/openjarvis/core/registry.py`, `src/openjarvis/agents/tool_resolver.py`, `src/openjarvis/agents/orchestrator.py` e `src/openjarvis/agents/loop_guard.py`. Observações dependem dessa versão do repositório e não substituem testes de integração.

## Diagnóstico do nosso projeto

A JARVIS atual é um assistente Python para Ubuntu GNOME Wayland, com FCC como backend Responses e ferramentas supervisionadas por `Toolkit`. Já foi validado em hardware real o inventário por Window Calls Extended e a ativação de Firefox por Activate Window By Title, com confirmação pelo GNOME Shell. Há SQLite para memória/planos e `/metricas` para latência da IA. Em teste real de foco, o total foi 13,44s, distribuídos em 9,385s e 1,998s de inferência e 2,057s restantes. Duas chamadas ao modelo ocorreram porque a primeira pediu inventário e a segunda pediu foco. A otimização `direct_tool_reply` eliminou necessidade de mais uma chamada de linguagem depois da confirmação da ferramenta, mas não dispensava a escolha de ferramentas.

## O que o OpenJarvis realmente oferece

1. **Separação de primitivas**: a raiz `src/openjarvis` contém `agents`, `core`, `tools`, `memory`, `engine`, `security`, `traces`, `skills`, `server`, `speech`, entre outros. Há presets `chat-simple`, `code-assistant`, `scheduled-monitor` etc. Isto permite evoluir componentes de forma independente, mas aumenta custo de integração.
2. **Registry + tool resolver**: `core/registry.py` implementa registros tipados (`AgentRegistry`, `ToolRegistry`, `EngineRegistry`, `RouterPolicyRegistry` etc.). `agents/tool_resolver.py` resolve instâncias de ferramentas, esquemas e recursos, priorizando capacidades do agente, ferramentas configuradas e adaptadores MCP. A vantagem é anunciar somente ferramentas apropriadas ao contexto e separar isso de permissões de execução.
3. **Orquestrador**: `agents/orchestrator.py` contém loop de chamadas de ferramentas e gancho `before_tool_call` com negação conservadora em falhas de governança. É uma referência para autorização no ponto de execução, mas o nosso `Toolkit.approve` e as verificações de efeito devem permanecer.
4. **Loop guard**: `agents/loop_guard.py` detecta chamadas idênticas, ciclos A-B-A-B, polling excessivo e oferece compressão de contexto. Atualmente nossa JARVIS já deduplica assinatura por turno em `agent.py`; no futuro vale adicionar alerta/bloqueio de ciclos entre ferramentas sem repetir operações locais.
5. **Local-first e medição**: OpenJarvis prioriza execução local e métricas de energia, latência, tokens/custo. Nosso produto depende do FCC e extensões GNOME, e não deve herdar motores de inferência ou bibliotecas pesadas só para reproduzir arquitetura.

## O que vamos reaproveitar (design, não copiar infraestrutura)

| Padrão OpenJarvis | Aplicação na nossa JARVIS | Prioridade |
| --- | --- | --- |
| Resolução por capacidades (`tool_resolver`) | `router.tool_catalog` anuncia somente `focus_window` em foco inequívoco ou `desktop_windows` em listagem simples | **Implementado nesta etapa** |
| Métricas e avaliações de latência | `/metricas` adiciona `tools_advertised` para quantificar redução do catálogo (não garante redução proporcional do tempo do provedor) | **Implementado nesta etapa** |
| Engine independente de agentes | Definir interface estável de clientes `responses()` para FCC e eventualmente motor local; não trocar o FCC agora | Depois |
| Loop guard e limites de polling | Evitar repetição entre ferramentas e limitar chamadas redundantes sem perder verificações obrigatórias | Depois |
| Traces por ferramenta | Guardar decisões e resultado sanitizado das verificações com correlação entre requisições, sem armazenar segredos | Depois |
| Plugins e `skills` | Registro tipado de capacidades sob controle do usuário, mantendo políticas do `Toolkit` | Depois |
| Desktop GUI e voz | Interfaces opcionais sobre o mesmo backend, sem reescrever o núcleo | Etapas posteriores |

## Escolha técnica implementada: catálogo de ferramentas enxuto

`router.tool_catalog` mantém todas as ferramentas autorizadas em solicitações complexas e incertas. Apenas pedidos *inequívocos* de foco de uma janela anunciam `focus_window`. Perguntas simples para listar janelas anunciam `desktop_windows`.

**Atenção:** resolver ferramentas para a IA **não autoriza executar ações**. `Toolkit.execute` continua aplicando restrições, e `focus_window` exige consentimento e relê o GNOME depois. Filtro não pode ser confundido com firewall ou controle de permissão. A ação em si mantém as mesmas validações.

**Objetivo do experimento:** reduzir tamanho do catálogo enviado ao modelo e potencialmente uma rodada de inferência. O comportamento real do FCC precisa ser medido: casos similares com `model_rounds`, `model_s`, `tools_advertised` e `total_s`. A redução de latência **não está comprovada** até realizar novo teste físico.

## O que não copiar agora

- Núcleo inteiro do OpenJarvis: arquitetura de framework grande demais para nosso estágio.
- Inicialização automática do Ollama, Rust nativo, conectores e dependências numerosas: alterariam o ambiente do notebook e poderiam introduzir conflitos, inclusive nome do CLI `jarvis`.
- Ferramentas com acesso irrestrito ao shell, instalação automática de skills de terceiros ou execução de código arbitrário: enfraqueceriam nossas aprovações e restrições.
- Código licenciado Apache-2.0 sem manter avisos e requisitos da licença: nesta etapa usamos **inspiração arquitetural**, não copiamos trechos de terceiros.

## Próximo teste no notebook

1. `cd ~/free-jarvis && git pull --ff-only origin main && source .venv/bin/activate && jarvis-fcc`
2. `Jarvis, coloque o Firefox em primeiro plano.` (Firefox já em foco ou não). Observe autorização quando aplicável.
3. `/metricas`: esperamos `tools_advertised: 1`, `model_rounds: 1` e `direct_tool_reply: true` se a IA chamar uma vez `focus_window`.
4. `Jarvis, quais janelas estão abertas no meu computador?`; `/metricas`: esperamos catálogo 1 (`desktop_windows`); esse pedido exige segunda chamada para a IA formatar o inventário.
5. Se `tools_advertised` não for 1, verifique a redação exata. Pedidos complexos recebem catálogo inteiro intencionalmente.

## Fontes

- https://github.com/open-jarvis/OpenJarvis/blob/main/README.md
- https://github.com/open-jarvis/OpenJarvis/blob/main/src/openjarvis/core/registry.py
- https://github.com/open-jarvis/OpenJarvis/blob/main/src/openjarvis/agents/tool_resolver.py
- https://github.com/open-jarvis/OpenJarvis/blob/main/src/openjarvis/agents/orchestrator.py
- https://github.com/open-jarvis/OpenJarvis/blob/main/src/openjarvis/agents/loop_guard.py
- https://github.com/open-jarvis/OpenJarvis/blob/main/LICENSE
