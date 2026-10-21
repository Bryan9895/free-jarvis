# Plano de desenvolvimento — JARVIS FCC

## Objetivo
Assistente pessoal open-source em português, com FCC como gateway de modelos, execução local modular, permissões explícitas e suporte futuro a voz e desktop Wayland.

## Etapa 0 — arquitetura e contratos (implementado)
- Interface inicial de terminal, separação entre FCCClient, Agent, Toolkit, Memory.
- Protocolo FCC /v1/responses e /v1/models.
- Ambiente configurado via variáveis; não armazenar token no Git.
- Ferramentas com execução limitada ao workspace e aprovação por alteração.

## Etapa 1 — MVP texto (implementação inicial)
- Conversa via terminal e contexto recente em SQLite.
- Ferramentas: listar, ler, escrever arquivo; executar comandos restritos; abrir URL.
- Git/GitHub CLI para operações de inspeção (sem push automático).
- Testes locais unitários com cliente FCC simulado.

**Gate**: testar manualmente com fcc-server e provedor real; verificar o suporte do FCC à reprodução explícita de ferramentas antes de declarar integração completa.

## Etapa 2 — execução de ferramentas robusta
- Tratar histórico de chamadas de ferramentas sem depender de retenção de respostas do servidor, se necessário.
- Implementar escrita atômica, backups, limites de saída e auditoria estruturada.
- Conjunto de ações Git (clone, branch, commit, PR) com aprovações granulares e isolamento do projeto.
- Logs com mascaramento de segredos e confirmação com diff.

## Etapa 3 — navegador
- Adicionar Playwright em processo próprio com perfil isolado.
- Ferramentas: abrir, observar DOM, clicar, digitar e screenshot sob autorização.
- Testar com páginas de demonstração; nunca presumir acesso ao Firefox pessoal.

## Etapa 4 — voz e memória
- STT local com whisper/faster-whisper, TTS Piper; voz como camada opcional.
- Palavra de ativação local, push-to-talk, seleção de dispositivos.
- Memória de longo prazo explicitamente revisável; exclusão de históricos.

## Etapa 5 — desktop Wayland
- Identificar compositor (XDG_CURRENT_DESKTOP) e suporte do portal org.freedesktop.portal.RemoteDesktop/ScreenCast.
- Solicitar autorização visível por sessão; implementar controle mediado por portal.
- Confirmar visualmente resultados; sem sudo global, keylogging ou bypass de permissões.

## Etapa 6 — interface, estabilidade e lançamento
- Interface com PySide6 (chat, voz, lista de ações, permissões).
- Testes de integração, isolamento de diretórios, pacotes e scripts Linux.
- CI GitHub Actions (testes sem credenciais), documentação, release e demo.

## Critérios transversais
- Cada ação deve ser done, unverified, failed ou rejected.
- Alterações no disco/GitHub/desktop necessitam aprovação conforme o risco.
- LLM não executa texto de páginas ou arquivos como instruções privilegiadas.
- Suportar funcionamento limitado/offline quando o provedor externo falhar.

## Registro de desenvolvimento — 2026-10-21
- Etapa 2 iniciada: melhorias no loop de ferramentas e segurança de argumentos.
- Respostas do FCC agora são verificadas antes de uso, chamadas são repetidas com seus `call_id`, e o limite de rodadas impede execução ilimitada.
- O terminal usa lista de comandos **exatos**; não permite novos argumentos arbitrários.
- Testes de regressão adicionados em `tests/test_core.py` e CI em `.github/workflows/tests.yml`.
- **Validação local:** 5 testes novos passaram com cliente FCC simulado (sem servidor real). Os testes anteriores permanecem no repositório, mas ainda precisam rodar no CI da branch.
- **Pendente:** teste real com `fcc-server` e provedor que suporte function calling; operações Git aprovadas, snapshots, backups e auditoria de alterações.
- **Limitação de segurança conhecida:** escrita ainda não é atômica; não usar para arquivos sensíveis ou projetos sem backup. Para a próxima entrega: escrita segura e conferência de alterações.

## Etapa 3 — implementação inicial (2026-10-21)
- Novo `browser_worker.py` utiliza Chromium headless via Playwright em subprocesso separado, sessão temporária e downloads desativados.
- Novo `browser.py` controla o processo por linhas JSON; fechamento do agente encerra navegador.
- Ferramentas do modelo: `browser_navigate`, `browser_inspect`, `browser_click`, `browser_fill` e `browser_screenshot`.
- Ações de navegação, clique, preenchimento e screenshot requerem confirmação manual; leitura da página é permitida.
- Filtro básico recusa file://, localhost, endereços privados e reservados, também nos recursos do Chromium.
- O assistente não acessa as abas/cookies do Firefox pessoal; screenshots ficam no workspace.
- Testes unitários sem rede em `tests/test_browser.py`; testes reais com Chromium e FCC ainda precisam ser validados em Linux Wayland.
- **Limitações de segurança:** DNS pode mudar entre validação e requisição (DNS rebinding); não utilizar o navegador automatizado com contas ou segredos sensíveis nesta versão. Clique pode desencadear ações externas apesar da aprovação; mantenha uma sessão de demonstração. Página pública não é uma fonte de instruções confiáveis.

## Registro — etapa 3 validada no CI (2026-10-21)
- Execução GitHub Actions: https://github.com/Bryan9895/free-jarvis/actions/runs/39665012635
- Jobs `test` e `browser-e2e` concluídos com **success**; o Chromium foi instalado e o teste em HTML local verificou inspeção, preenchimento, clique e screenshot.
- O teste **não** cobre servidor FCC real, navegador pessoal, login ou Wayland gráfico nativo. Bloqueio de DNS rebinding e política de novos pop-ups ainda exigem endurecimento.

## Etapa 4 — primeira entrega (2026-10-21)
- `src/jarvis/voice.py`: gravação local temporária com sounddevice, transcrição faster-whisper int8 na CPU e síntese com Piper CLI.
- `jarvis --voice`: solicitação de gravação ao pressionar Enter, janela de 6 segundos; mantém entrada de texto e confirmações da etapa 2.
- Padrão seguro: nenhuma gravação contínua; sem Piper configurado, apenas texto; arquivos WAV temporários são excluídos.
- `tests/test_voice.py`: testes simulados de transcrição, TTS e limpeza, sem acesso a microfone real.
- Dependências opcionais em `pip install -e '.[voice]'`.
- **Ainda pendente nesta etapa**: instalação/teste físico no Ubuntu do usuário, dispositivo de entrada selecionável, palavra de ativação local, detecção de silêncio e ajustes de latência. Não confundir o protótipo com reconhecimento de voz finalizado.

## Diagnóstico e seleção automática de modelos FCC — entrega 2026-10-21
- Cliente usa `GET /v1/models?view=responses`, não a lista de aliases da interface Claude.
- Se `FCC_MODEL` estiver ausente, seleciona o `default_model_id` do catálogo; `FCC_FALLBACK_MODELS` permite ordenar alternativas.
- Durante requisições de geração, troca de modelo em HTTP 429/500/502/503/504 ou falha de transporte. Nunca tenta mascarar 401/403. Em caso de troca, registra o novo modelo ativo.
- Novo `jarvis --check-fcc` consulta saúde, catálogo e envia uma requisição curta de inferência. O endpoint `/health` sozinho só prova que o processo HTTP está vivo.
- Testes de contrato simulados e teste HTTP local com servidor fictício adicionados. A execução real do FCC no Ubuntu permanece uma validação do usuário.
- **Privacidade**: troca automática entre provedores pode encaminhar o prompt a outro provedor. Para maior controle, restrinja os modelos expostos/configurados no FCC e configure `FCC_FALLBACK_MODELS` conscientemente.

## Etapa 5 — implementação parcial, respeitando Wayland
- `desktop_info`: informa sessão, compositor e detecção de portais usando DBus na sessão Linux.
- `desktop_screenshot`: solicita a captura pelo portal oficial XDG, com confirmação no terminal e janela nativa de permissão. A imagem é escrita no workspace, sem envio automático ao modelo.
- `desktop_open_app`: lança ID .desktop permitido em `JARVIS_ALLOWED_APPS` com aprovação; lançamento ainda precisa de confirmação visual para declarar sucesso.
- Dependência opcional `dbus-next`; testes unitários simulam diálogo e retorno de caminho do portal.
- **Ainda não implementado**: sessão `RemoteDesktop` completa (captura via PipeWire, libei/teclado, pointer), reconhecimento do conteúdo da captura pela IA, testes reais GNOME/Wayland e revogação centralizada de sessões. Não utilizar permissão ampla nem `sudo` para contornar o compositor.
