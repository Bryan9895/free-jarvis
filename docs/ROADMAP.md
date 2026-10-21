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
