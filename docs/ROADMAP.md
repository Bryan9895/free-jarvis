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
