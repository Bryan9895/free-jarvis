# Equipe multiagentes para desenvolver ADAM

Executável: `adam-team` / `python -m jarvis.engineering_team`.

Este é o **mecanismo de engenharia do projeto**, não um provedor novo do
assistente de voz. O fluxo é:

`Supervisor (FCC-CLAUDE) → Desenvolvedor (FCC-CLAUDE) → Codex crítico
→ Desenvolvedor corrige → Codex revê → testes → commit → GitHub opcional`.

Os comandos dos agentes são **injetados pelo operador** para não exigir um
modelo Anthropic nem sobrescrever a configuração FCC. Nenhum agente instala
conectores ou altera perfil do ADAM. Uso em branch/worktree limpa, nunca
diretamente em `main`.

## Exemplo (adaptar os comandos à sua instalação do FCC-CLAUDE)

1. Crie e abra um worktree em uma branch de desenvolvimento.
2. Crie `/tmp/adam-tarefa.txt` com a tarefa (não inclua chaves/senhas).
3. Exemplo apenas de formato (os comandos exatos variam conforme CLI):

```bash
adam-team --task-file /tmp/adam-tarefa.txt \
  --supervisor-cmd 'claude -p' \
  --developer-cmd 'claude -p' \
  --reviewer-cmd 'codex exec -' \
  --tests 'python -m unittest discover -s tests -q'
```

O programa passa as instruções por `stdin`, não executa shell e **não**
habilita autoaprovação/bypass de permissões. Ajuste flags conforme as versões
instaladas no Ubuntu. `--push` publica apenas a branch já aprovada, e apenas
depois de testes bem-sucedidos; não abre nem integra PR automaticamente.

Esta ferramenta tem **testes de protocolo/mocks**, mas o ciclo real
FCC-CLAUDE + Codex no seu worktree ainda precisa ser validado. Não é
prova de qualidade do modelo ou de aceitação física.
