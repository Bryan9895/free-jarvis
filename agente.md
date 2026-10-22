# Plano de implementação — JARVIS como assistente pessoal

## Objetivo e critérios de sucesso

A JARVIS deve funcionar no Ubuntu GNOME Wayland como uma assistente pessoal em português. O usuário aperta para falar, a fala é transcrita localmente, o Free Claude Code (FCC) recebe o texto pela API Responses, decide respostas e chamadas de ferramentas, e a resposta é reproduzida por síntese de voz local. O FCC é o gateway de modelos; esta meta não depende de uma API de áudio nativa do FCC.

O resultado final deve permitir que o usuário peça, em linguagem natural, para inspecionar o computador, abrir, focar, organizar e fechar aplicativos e janelas, manipular arquivos, executar tarefas de desenvolvimento e criar projetos completos. O fluxo de desenvolvimento inclui dependências, testes, Git e GitHub. A assistente deve mostrar o que executou e distinguir resultado comprovado de ação apenas enviada ao sistema.

"Acesso total" significa acesso amplo às capacidades concedidas pelo usuário e pelo sistema operacional. A JARVIS pode operar na conta do usuário e, quando uma tarefa administrativa exigir, solicitar autenticação por `sudo`/polkit. Ela não deve contornar permissões do GNOME Wayland nem guardar senha de administrador. Uma autorização de sessão pode dispensar confirmações internas repetidas, mas não substitui diálogos e autenticação nativos.

## Estado encontrado no repositório (22/10/2026)

| Área | Existe hoje | Falta para a meta |
| --- | --- | --- |
| FCC e agente | `fcc.py` usa `/v1/models` e `/v1/responses`; `agent.py` executa chamadas de ferramentas com limite de rodadas; há diagnóstico e seleção de modelo. | Testes reais de contrato com modelos aptos a ferramentas, recuperação robusta de falhas e relato consistente de resultados em tarefas longas. |
| Voz | `voice.py` grava até 15 segundos, transcreve com faster-whisper e usa Piper opcional; `--voice` inicia gravação de 6 segundos por Enter. | Botão de apertar para falar, início/fim de gravação pelo usuário, seleção de dispositivos, reprodução confiável, latência e testes com hardware real. |
| Arquivos e projetos | Ferramentas criam/leem/escrevem/movem arquivos, criam projeto Python mínimo e abrem projetos no editor; raízes são limitadas a `JARVIS_WORKSPACE` e `JARVIS_ALLOWED_DIRS`. | Edição segura de múltiplos arquivos, diffs, escrita atômica, execução de build/testes, instalação de dependências e suporte a projetos além do esqueleto Python. |
| Planejamento | Planos de até cinco etapas são persistidos em SQLite e retomados com decisão explícita para etapas incertas. | Planos de desenvolvimento maiores, checkpoints por operação, dependências entre etapas e retomada baseada em evidências. |
| Desktop | Há inventário e foco de janelas, minimizar/restaurar/maximizar e layout; algumas ações dependem de extensões GNOME opcionais. Captura e entrada RemoteDesktop são experimentais. | Fechar janela/aplicativo com identificação inequívoca, sessão de controle gráfico utilizável, observação de tela ligada às ações e validação real de cada operação. |
| Navegador e GitHub | Playwright usa navegador isolado; comandos de terminal são uma lista curta de inspeção. | Fluxos de navegação mais completos e operações Git/GitHub de escrita com verificações. |
| Autorização | `--auto-approve` dispensa confirmações internas da sessão para ferramentas atuais. | Concessão de capacidades para a sessão, revogação imediata, limites de tarefa e trilha de auditoria que cubra também novas ferramentas. |

Os testes automatizados existentes simulam parte do desktop e do FCC. Uma função documentada como implementada não deve ser marcada como validada no notebook até haver evidência do GNOME/FCC real. `docs/RETOMADA.md` registra os testes manuais já confirmados e os que ainda faltam.

## Arquitetura e contratos a implementar

1. **Entrada e saída:** criar uma camada de interação única para terminal e futura interface gráfica. O evento de apertar para falar inicia a gravação; soltar termina e envia a transcrição. Texto digitado usa o mesmo fluxo de tarefas. O áudio sintetizado reproduz exatamente a resposta final mostrada ao usuário. Se microfone, STT ou TTS falhar, a conversa continua por texto e informa o erro.
2. **Executor de capacidades:** manter o FCC como planejador, mas executar somente ferramentas registradas localmente. Cada chamada recebe argumentos validados, escopo de sessão, prazo, identificador de operação e resultado estruturado. Nunca tratar texto do modelo, de arquivos ou de páginas como autorização. O estado de uma ação deve ser `verified`, `unverified`, `failed` ou `rejected`, acompanhado da evidência disponível.
3. **Sessão autônoma:** o usuário inicia uma sessão com concessões explícitas para arquivos, processos, desktop, navegador, rede/GitHub e administração. A concessão vale até o fim da sessão ou revogação; cada ação fica visível no log. A JARVIS deve interromper novas ações imediatamente após revogação. Autenticação administrativa e permissões dos portais continuam sendo solicitadas pelo sistema quando necessárias.
4. **Projetos:** toda tarefa de desenvolvimento tem diretório de projeto definido. O executor usa comandos sem shell implícito, com diretório de trabalho, limite de tempo, saída limitada e ambiente registrado; oferece diff antes de aplicar alterações importantes e verifica arquivos após gravar. Instalação de dependências ocorre no ambiente do projeto quando possível. Git/GitHub mostram branch, diff e resultado remoto antes de declarar a operação concluída.
5. **Desktop:** preferir APIs do compositor, portais e extensões GNOME já usadas. Identificar a janela por ID e metadados atuais; revalidar imediatamente antes de agir e observar o estado depois. Para fechamento, distinguir fechar uma janela de encerrar um processo. Se houver múltiplas correspondências, pedir desambiguação. Entrada gráfica genérica depende de sessão RemoteDesktop autorizada e observação da tela, com parada fácil pelo usuário.
6. **Persistência:** guardar objetivos, etapas, chamadas, resultados e verificações no SQLite existente, sem gravar senhas ou tokens. Após uma interrupção, marcar operações sem confirmação como incertas; consultar o estado antes de repetir qualquer mutação.

## Ordem de implementação

**Prioridade atual:** o roadmap v0.5.0–v1.0.0 fornecido pelo usuário define a sequência de entregas. Iniciar pelo gerenciamento avançado de janelas da v0.5.0; manter as melhorias transversais da Fase 1 abaixo como suporte ao executor. Não declarar v0.5.0 concluída antes de layouts de três ou mais janelas, perfis e validação física no Ubuntu.

**Progresso adicional da v0.5.0:** ferramenta de grade para três/quatro janelas e perfis nomeados em SQLite implementados com seleção sem ambiguidade, revalidação após aprovação e conferência da geometria. A validação real no GNOME e eventual refinamento dos perfis permanecem pendentes.

**Validação física (22/10/2026):** posição `custom`, centro, consulta de foco, fechamento, histórico SQLite, grades de três/quatro janelas e restauração de perfil passaram em GNOME Wayland com XTerm descartável. `MoveResize` exigiu `Move` separado para aplicar posição; `GetFocused` exigiu interpretar `uint64` do `gdbus`. A v0.5.0 ainda requer validação de aplicativos cotidianos, diálogo de salvamento e monitor adicional quando disponível antes de ser lançada. Em seguida, iniciar v0.6.0 pelo inventário de monitores e áreas de trabalho.

**Início da v0.6.0 (22/10/2026):** `desktop_spaces` fornece inventário validado e somente leitura de monitores e áreas de trabalho via Window Control. Confirmado no GNOME real com um monitor e duas áreas. Próximos itens: alternar áreas, mover janelas entre áreas/monitores com revalidação e observação do resultado, criar perfis de ambientes e validar com monitor adicional quando disponível.

**Progresso da v0.6.0:** `activate_workspace` e `move_window_to_workspace` revalidam área e janela após autorização e exigem estado observado para confirmar sucesso. Teste real com XTerm descartável confirmou movimento para a segunda área e volta, além de alternância e restauração da área ativa. Movimento entre monitores foi implementado na etapa seguinte, abaixo.

**Movimento entre monitores:** `move_window_to_monitor` implementado com identificação inequívoca, topologia estável e confirmação de `monitor_index` pelo GNOME. Teste real com monitor único confirmou `not_found`/`already_in_state`; testes simulados cobrem movimento entre monitores. A validação física com dois monitores permanece pendente. Próximo item de código: perfis de ambiente envolvendo aplicativos, áreas e monitores.

**Perfis de ambiente:** `save_desktop_profile`, `list_desktop_profiles` e `restore_desktop_profile` salvam e restauram aplicativos, monitor, área e geometria com resultado por etapa. Aplicativo ausente só é aberto quando o perfil inclui `app_id` XDG; abertura enviada e não observada bloqueia repetição automática. Teste real confirmou duas XTerm e abertura/restauração da Calculadora GNOME. Validação com dois monitores segue pendente. Próxima prioridade de código: v0.7.0, registro central de ferramentas e permissões por capacidade.

**Progresso da Fase 1 (22/10/2026):** `write_file` agora mostra um diff limitado na autorização, aceita `expected_sha256` para detectar conteúdo desatualizado, recusa mudanças concorrentes e substitui o arquivo por escrita temporária atômica. `/permissoes revogar` bloqueia novas chamadas de ferramenta até o usuário escolher novamente o modo de autorização. A suíte automatizada passou; auditoria persistente e os demais itens da fase seguem pendentes.

### Fase 1 — executor e verificações

- Definir contratos de ferramenta, autorização de sessão, auditoria e resultado com evidência; integrar em `Agent`, `Toolkit`, `ApprovalPolicy` e planejador.
- Adicionar escrita atômica, diffs, tratamento de conflitos, limites de saída e testes de interrupção/retomada. Preservar arquivos já existentes quando uma etapa falhar.
- **Concluída quando:** uma tarefa com várias alterações mostra cada ação e seu estado real, uma recusa ou revogação interrompe a execução, e reiniciar a JARVIS não repete mutações incertas.

### Fase 2 — desenvolvimento de projetos

- Adicionar ferramentas parametrizadas para executar programas, testes e builds no diretório do projeto; criar ambientes de desenvolvimento e instalar dependências com escopo e prazo definidos.
- Implementar criação e edição de projetos de múltiplos arquivos, inspeção de erros, correção iterativa e ações Git/GitHub (branch, commit, push e PR) com verificação de resultado.
- **Concluída quando:** a JARVIS cria um projeto pequeno a partir de pedido verbal ou textual, implementa uma mudança, roda testes, corrige uma falha reproduzível e prepara/publica a alteração no GitHub conforme a concessão da sessão.

### Fase 3 — controle do computador

- Consolidar inventário, foco, abertura, estado, layout e fechamento de janelas; acrescentar gerenciamento dos processos que a JARVIS iniciou.
- Transformar o experimento RemoteDesktop em uma sessão de ponteiro/teclado autorizada e revogável, combinada com captura/observação de tela. Usar interação gráfica quando não houver ferramenta semântica mais confiável.
- **Concluída quando:** no Ubuntu real, a JARVIS abre, identifica, organiza e fecha uma janela solicitada, lida corretamente com duas janelas do mesmo aplicativo e relata falha ou resultado incerto sem inventar sucesso.

### Fase 4 — conversa por voz

- Substituir a gravação fixa por apertar para falar com indicador de gravação, seleção de microfone/saída, detecção de silêncio opcional e cancelamento; manter STT e TTS locais.
- Integrar transcrição, planejamento, execução, resposta falada e fallback textual no mesmo fluxo; medir latência por etapa.
- **Concluída quando:** o usuário conclui uma tarefa de projeto e uma tarefa de desktop por voz, consegue interromper a gravação ou a execução e recebe resposta audível com o mesmo estado exibido no texto.

### Fase 5 — validação e entrega

- Rodar testes unitários e de integração sem credenciais no CI; testar separadamente FCC real, microfone/alto-falante e GNOME Wayland no notebook.
- Documentar instalação, extensões/portais opcionais, configuração de capacidades, revogação, recuperação de tarefas e limitações observadas. Preparar uma interface simples para estado da sessão, tarefas, permissões e voz.
- **Concluída quando:** um roteiro de ponta a ponta reproduz os cenários de voz, projeto, GitHub e desktop após instalação limpa, com logs suficientes para explicar qualquer falha.

## Cenários mínimos de aceite

- Criar projeto, editar dois arquivos, executar teste com falha, corrigir e executar novamente; conferir diff e estado final.
- Autorizar sessão autônoma, realizar várias ações sem confirmações internas, revogar a sessão e comprovar que a próxima ação foi rejeitada.
- Solicitar instalação administrativa; usar autenticação nativa e registrar sucesso, recusa ou falha sem guardar senha.
- Abrir, focar, mover e fechar aplicativo no GNOME; repetir com duas janelas semelhantes e exigir desambiguação.
- Interromper a JARVIS durante uma alteração e retomá-la sem repetir uma ação de resultado incerto.
- Falar uma solicitação por botão, obter transcrição, execução via FCC e resposta por áudio; desconectar microfone ou FCC e confirmar fallback/erro claro.

## Premissas

- Plataforma inicial: Ubuntu GNOME Wayland; outros sistemas ficam para uma fase posterior.
- Interface de voz principal: apertar para falar. STT/TTS são locais; o FCC recebe e devolve texto e chamadas de ferramentas.
- A concessão ampla é limitada à sessão iniciada pelo usuário. Permissões do sistema e autenticação administrativa continuam sob controle do sistema operacional.
