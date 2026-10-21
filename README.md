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

## Etapa 3 — Navegador automatizado (Playwright)

A JARVIS controla um **Chromium isolado e headless**, sem utilizar as sessões ou os cookies do Firefox pessoal. Isso funciona no Ubuntu com Wayland porque o navegador automatizado não depende de controlar as janelas do desktop.

Instalação opcional do navegador:

```bash
git pull origin main
source .venv/bin/activate
pip install -e '.[browser]'
python -m playwright install chromium
```

Em algumas instalações Linux, o Chromium requer pacotes do sistema adicionais; consulte `python -m playwright install --with-deps chromium` (o comando pode solicitar instalação de dependências via apt).

Execute `jarvis` com `fcc-server` ativo e `FCC_MODEL` configurado. Exemplo:

> "Abra https://example.com no navegador isolado, leia o título e descreva a página."

Ferramentas disponíveis: `browser_navigate` (abre URL), `browser_inspect` (lê DOM e elementos), `browser_click` (clica por seletor CSS), `browser_fill` (preenche campos) e `browser_screenshot` (salva PNG no workspace).

**Aprovações:** navegar, clicar, digitar e capturar a tela requerem digitar `SIM` no terminal. A inspeção de páginas já abertas não solicita confirmação. Não use a automação com contas pessoais ou informações sigilosas até concluirmos o endurecimento da segurança de rede; o filtro de IP não elimina todos os riscos de DNS rebinding. Não há execução de JavaScript arbitrário solicitado pela IA, download de arquivos ou perfil persistente.

Testes sem navegador: `python -m unittest discover -s tests -v`.

**Próximos passos:** testes E2E de navegação em site de demonstração, verificação de resposta FCC real e melhorias de auditoria/isolamento.

## Etapa 4 — entrada e saída de voz local (MVP)

O modo de voz é **opcional**. O chat tradicional continua disponível.

No Ubuntu/Debian, instale os dispositivos de áudio e a síntese:
```bash
sudo apt install -y libportaudio2 alsa-utils
python3 -m pip install -e '.[voice]'
python3 -m pip install piper-tts
```
O `faster-whisper` usa CPU com quantização int8. Na primeira utilização, o modelo de transcrição precisa ser baixado; depois ele fica em cache. Selecione `tiny` para um computador com RAM limitada.

Para ouvir as respostas, obtenha de uma fonte confiável um modelo de voz **Piper compatível com português**, incluindo seu arquivo `.onnx.json` ao lado do `.onnx`:
```bash
export JARVIS_WHISPER_MODEL=tiny
export JARVIS_LANGUAGE=pt
export JARVIS_PIPER_MODEL="$HOME/Modelos/piper/pt_BR-voz.onnx"
jarvis --voice
```
Substitua o caminho de exemplo pelo nome real do modelo baixado. Sem `JARVIS_PIPER_MODEL`, a transcrição e o chat continuam funcionando e a resposta aparece apenas em texto.

**Como usar:** pressione **Enter** na CLI para gravar 6 segundos, aguarde a transcrição e a resposta. Também é possível digitar uma mensagem diretamente. Digite `sair` para encerrar.

**Privacidade:** microfone inativo fora das gravações; WAV temporário apagado após transcrição. Transcrição e TTS são locais, porém o texto reconhecido é enviado ao modelo configurado no FCC, que pode usar provedor remoto. Não há escuta constante nem ativação por palavra-chave nesta primeira versão.

**Limitações:** a gravação ainda tem duração fixa (não é push-to-talk contínuo); a seleção do dispositivo depende da configuração padrão do sistema. Testes de microfone real e Piper real precisam ser feitos no Ubuntu do usuário.
