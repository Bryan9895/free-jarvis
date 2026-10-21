# JARVIS FCC — MVP 0.1

Assistente pessoal em Python usando [Free Claude Code](https://github.com/Alishahryar1/free-claude-code) como gateway para modelos de IA.

**Estado:** MVP de terminal. A integração real com FCC requer validação no computador do usuário.

## Funcionalidades atuais

- Cliente HTTP para `/health`, `/v1/models` e `/v1/responses`.
- Conversa com chamadas de ferramentas e histórico SQLite.
- Workspace restrito para listagem, leitura e escrita autorizada.
- Terminal apenas para inspeção, GitHub CLI (consulta) e abertura de URLs com confirmação.

Ainda não há voz, interface gráfica nem controle Wayland. Veja `docs/ROADMAP.md`.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
mkdir -p ~/Projetos
export FCC_URL=http://127.0.0.1:8082
export JARVIS_WORKSPACE="$HOME/Projetos"
jarvis --health
jarvis --models
export FCC_MODEL='ID_DO_MODELO'
jarvis
```

Configure `FCC_TOKEN` no ambiente caso o proxy exija autenticação. **Não publique credenciais.**

## Testes

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Segurança

Comandos arbitrários e `sudo` não estão habilitados. Escritas requerem confirmação. O histórico SQLite não é criptografado; não envie segredos nas conversas. O projeto não foi testado de ponta a ponta com um servidor FCC real.
