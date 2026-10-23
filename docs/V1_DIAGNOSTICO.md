# Diagnóstico e definição verificável da v1.0

Referência: `2043a4f` em 22/10/2026. Teste inicial: `python -m unittest discover -s tests -q`, **282 testes passaram**. Avisos existentes de `ResourceWarning` e coroutine não aguardada apareceram na suíte; não são falhas introduzidas nesta branch. O pacote declara `0.4.0`.

## Estado confirmado

| Recurso | Implementado | Teste automático | Validação física registrada | Pendente para v1.0 |
| --- | --- | --- | --- | --- |
| FCC, modelos, fallback e chat | Sim | Sim, com cliente/HTTP simulado | FCC real: health, catálogo, inferência e chat passaram; gpt-oss realizou tool call; gpt-5.6-luna não emitiu tool call estruturada | Provedor cancelável; compatibilidade de ferramentas depende do modelo |
| Arquivos e projetos | Sim, com escrita atômica e raízes | Sim | Criação real em workspace temporário conferida por SHA-256 | Ensaios com alteração concorrente e conjunto cotidiano |
| Planos SQLite e retomada | Sim, até 5 etapas, com dependências explícitas | Sim | Plano real de escrita executado e verificado em workspace temporário | Queda/reinício real e cancelamento durante chamada |
| GNOME: janelas e layouts | Sim, extensões opcionais | Sim, inventários simulados | XTerm/Calculadora; centralização e layouts Tk; Firefox e VS Code descartáveis lado a lado nesta execução | Terminal cotidiano, diálogo de salvamento |
| GNOME: monitores e áreas | Sim | Sim | Áreas; janela Tk movida entre HDMI e eDP com confirmação GNOME | Repetir em uso cotidiano e validar perfil em dois monitores |
| Perfis de ambiente | Sim | Sim | XTerm e Calculadora | Perfil em dois monitores físicos |
| Navegador Playwright | Sim, subprocesso isolado | Sim, página local | Teste controlado local passou: navegar, inspecionar, preencher, clicar e capturar | DNS rebinding e comportamento em sites externos permanecem limitados |
| Voz | Opcional e carregada sob demanda; faster-whisper e Piper pt-BR instalados | Sim, incluindo ausência/silêncio | Piper sintetizou fala; faster-whisper transcreveu áudio sintético em português; fontes PipeWire enumeradas | Usuário testar push-to-talk com a própria fala, qualidade e latência no microfone |
| GUI | Tkinter opcional sobre `JarvisService` | Backend/headless testado | Janela aberta/fechada no GNOME com serviço simulado | Fluxo da GUI com FCC real, aprovação e cancelamento físicos |
| Permissões/capacidades | Sim | Sim | Portal detectado na sessão atual | Revogação/cancelamento em trabalho em curso, confirmação pontual de perda de dados |

## Medições e validações desta execução

Ambiente: Ubuntu/Linux x86_64, Python 3.14.4, GNOME Shell 50.1, Wayland, 7.2 GiB de RAM total. São medições locais desta sessão, sem comparação com uma versão anterior:

- Instalação editável limpa em venv temporária; CLI `--doctor` e `--help` executados fora do repositório.
- Inicialização do `--doctor`: cinco execuções, mediana **0,152 s**.
- GUI Tkinter com FCC real: resposta a `GUI_OK` em **1,63 s**; pico RSS do processo medido em **45.272 KiB** durante conversa.
- Chat FCC em terminal: **2,17 s**; gravação real com gpt-oss e conferência SHA-256: **9,86 s**; plano real de escrita verificada: **16,85 s**. Latência depende do modelo e do servidor.
- Depois de reduzir o catálogo para uma ferramenta, gravação real com gpt-oss concluiu em **4,33 s**; `tools_advertised=1`, `state=verified`. Tempos não são diretamente comparáveis entre solicitações/modelo/carga.
- Controle desktop físico em janelas Tk de teste: centralização e layout de duas janelas retornaram `geometry_verified` e `layout_verified`; seleção de títulos sobrepostos retornou `ambiguous`.
- Topologia atual observada: um monitor de 1366×768 e duas áreas de trabalho; isso não valida movimento entre monitores.
- Navegador Chromium em página de teste local: navegar, inspecionar, preencher, clicar e capturar passaram. Microfone não foi validado fisicamente.
- O workflow remoto do GitHub Actions não foi executado nesta branch local. A matriz de testes foi executada com Python 3.14; o workflow declara Python 3.11, indisponível nesta máquina.
- Continuação após o checkpoint: testes de navegador E2E local, retomada e backend da GUI passaram; suíte completa: **310 testes passaram**. Planos aceitam strings legadas e objetos com `description`/`depends_on`; a etapa dependente só inicia quando sua dependência está `verified`.
- Diagnóstico atual: dependências browser/desktop/vision/voice e Piper instalados no `.venv`; pacote de voz Python inclui reconhecimento e síntese. Piper sintetizou voz pt-BR para WAV. PipeWire/PulseAudio expõe fontes de captura; áudio ainda não foi gravado. FCC acessível não implica inferência pronta até uma chamada de modelo.
- Python 3.11.16 foi instalado com uv em ambiente isolado `.venv311`; suíte completa (**310 testes**) e navegador E2E passaram nessa versão. GitHub Actions remoto não foi acionado.
- Dois monitores físicos conectados: HDMI 1920×1080 e eDP 1366×768. Movimento real de janela de teste entre eles foi verificado pelo inventário GNOME com `window_monitor_verified`.
- Layout físico com Firefox privado e VS Code em perfil descartável retornou `layout_verified`; ambas as janelas tiveram geometria lida novamente no GNOME. O VS Code de teste chegou ao limite de tamanho imposto pela tela interna (683×768), sem falha no layout. A janela privada foi fechada com `closed_verified`; processos Snap dos perfis de teste foram encerrados.
- Voz ponta a ponta sintética: Piper `pt_BR-faber-medium` produziu WAV mono 22.050 Hz; faster-whisper `tiny` transcreveu localmente a fala de teste em português. A transcrição aproximou a frase (“Davis teste local de reconhecimento de voz”), então o microfone real e a precisão ainda precisam ser conferidos pelo usuário. Nenhum áudio real foi gravado ou reproduzido.

O diagnóstico `jarvis-fcc --desktop-info` nesta sessão retornou GNOME Wayland e portais de captura/RemoteDesktop disponíveis. O ensaio separado de janela Tk confirmou movimentação entre monitores; o diagnóstico, por si só, não comprova captura de tela real. As 12 regressões listadas na solicitação do usuário têm testes distribuídos por `test_window_*`, `test_desktop_profiles`, `test_core`, `test_fcc*` e `test_execution_evidence`; manter a suíte como gate.

## Dependências externas

FCC e um modelo compatível com Responses/function calling; extensões GNOME Window Control e, para algumas operações, Activate Window By Title/Window Calls Extended; portal XDG; VS Code e aplicativos XDG para fluxos de abertura. Playwright/Chromium, Tkinter, sounddevice/faster-whisper e Piper são opcionais. O notebook alvo tem 8 GB: imports e processos pesados devem ocorrer somente ao usar cada capacidade.

## Mapa da estrutura atual para responsabilidades finais

| Responsabilidade | Código atual | Evolução incremental |
| --- | --- | --- |
| Domínio/resultados | estados em `planner.py`, `verification.py` e retornos de ferramentas | contrato pequeno em `execution_result.py`, sem dependência externa |
| Aplicação | `agent.py`, `planner.py`, `natural_tasks.py`, `service.py` | `JarvisService` compartilhado por interfaces; cancelamento cooperativo e persistência por etapa |
| Provedor | `fcc.py` | contrato de cliente e erros categorizados, mantendo FCC |
| Ferramentas/políticas | `registry.py`, `tool_specs.py`, `plugins.py`, `tools.py`, `approval.py` | validação no executor e módulos por responsabilidade; manter aliases de importação |
| Desktop | `window_*`, `desktop_*`, `monitor_control.py`, `wayland.py` | concentrar parsing D-Bus reutilizado, preservar adaptadores existentes |
| Navegador | `browser.py`, `browser_worker.py` | robustez do protocolo e efeitos verificados |
| Persistência | `memory.py`, `plan_store.py`, perfis SQLite | migrações não destrutivas por `PRAGMA user_version` |
| Interfaces | `cli.py`, `gui.py`, `voice.py` | GUI e CLI usam o mesmo serviço; voz é carregada sob demanda |
| Observabilidade | `Agent.last_metrics`, `Toolkit.operation_log`, `window_history.py` | IDs e eventos sanitizados correlacionados |

## Definição de concluído

A v1.0 exige os 15 critérios gerais da solicitação do usuário, instalação limpa, suíte e navegador controlado passando, GUI funcional e não bloqueante, voz opcional que não quebra texto, migração SQLite sem perda, cancelamento e retomada sem repetição cega. Cada resultado de ação deve distinguir recusa, indisponibilidade, ausência, ambiguidade, envio não verificado, parcial e sucesso verificado. Validação física de dois monitores e diálogos de salvamento será registrada separadamente; não declarar essas capacidades fisicamente validadas sem hardware/cenário. O número da versão só muda após esses gates.

Ficam para depois: reduzir falsos positivos/consumo da ativação contínua com testes longos no ambiente acústico real, outros sistemas operacionais, marketplace, cloud obrigatória e controle irrestrito.
