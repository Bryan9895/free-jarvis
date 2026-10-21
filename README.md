# JARVIS FCC — MVP 0.1

Assistente pessoal em Python usando [Free Claude Code](https://github.com/Alishahryar1/free-claude-code) como gateway para modelos de IA.

**Estado:** MVP de terminal. A integração real com FCC requer validação no computador do usuário.

## Funcionalidades atuais

- Cliente HTTP para `/health`, `/v1/models` e `/v1/responses`.
- Conversa com chamadas de ferramentas e histórico SQLite.
- Workspace restrito para listagem, leitura e escrita autorizada.
- Terminal apenas para inspeção, GitHub CLI (consulta) e abertura de URLs com confirmação.

Há protótipos de voz, navegador e diagnóstico Wayland; o controle global de mouse e teclado continua pendente. Veja `docs/ROADMAP.md`.

## Instalação para novos usuários — Ubuntu/Linux

> **IMPORTANTE:** entre na pasta `free-jarvis` antes de criar o ambiente virtual
> ou instalar os pacotes. Se você instalar a partir da pasta pai, o Python não
> encontrará `pyproject.toml` e poderá executar outro software chamado `jarvis`.

Se ainda não clonou o repositório:

```bash
git clone git@github.com:Bryan9895/free-jarvis.git
cd free-jarvis
```

Se já clonou em `~/Documentos/Projetos/Jarvis`:

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
```

Verifique a pasta correta; ambos os arquivos devem existir:

```bash
pwd
ls -l pyproject.toml src/jarvis/cli.py
```

Crie o ambiente **dentro desse repositório** e instale:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### Verificar se esta JARVIS está instalada

Use o comando específico **`jarvis-fcc`**, e não o genérico `jarvis`,
que pode pertencer a outro projeto (como OpenJarvis):

```bash
jarvis-fcc --doctor
jarvis-fcc --help
```

O diagnóstico mostra o caminho do módulo Python carregado e confirma a instalação
sem exigir FCC, microfone ou interface gráfica. Alternativa equivalente:

```bash
python -m jarvis --doctor
```

### Configurar e verificar o FCC

Inicie `fcc-server` em outro terminal e configure um provedor/modelo no painel
do Free Claude Code. Então:

```bash
mkdir -p "$HOME/Projetos"
export FCC_URL=http://127.0.0.1:8082
export JARVIS_WORKSPACE="$HOME/Projetos"

jarvis-fcc --health
jarvis-fcc --models
jarvis-fcc --check-fcc
```

`--health` só testa HTTP; `--check-fcc` faz uma **inferência real** usando o
provedor configurado, sujeito a quotas e cobrança. `FCC_MODEL` é **opcional**;
por padrão escolhemos o modelo anunciado pelo FCC e tentamos fallback em erros
transitórios. Não coloque `ID_DO_MODELO` literalmente: escolha um ID real de
`--models` caso queira fixar o principal.

Iniciar chat:

```bash
jarvis-fcc
```

Instale as capacidades extras somente depois do diagnóstico básico:

```bash
python -m pip install -e '.[browser,desktop]'
python -m playwright install chromium
jarvis-fcc --desktop-info
```

O modo de voz requer `python -m pip install -e '.[voice]'`, além das dependências
de áudio descritas abaixo. **Não é necessário recriar outro ambiente virtual
na pasta pai.** Nenhum teste do GitHub Actions acessa o FCC instalado em seu PC.

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

## API FCC — autodescoberta e troca automática de modelo

O cliente usa `/v1/models?view=responses` para identificar IDs compatíveis com o endpoint `/v1/responses`. **A variável `FCC_MODEL` agora é opcional.** Se não estiver definida, o sistema utiliza o modelo padrão anunciado pelo FCC; em falhas transitórias HTTP 429/500/502/503/504, tenta outros modelos anunciados pelo servidor.

Configure opcionalmente preferências para prioridades explícitas:
```bash
export FCC_URL=http://127.0.0.1:8082
# export FCC_TOKEN=...   # somente se o proxy exigir autenticação
# export FCC_MODEL='id-preferido'
# export FCC_FALLBACK_MODELS='id-secundario,id-terciario'
jarvis --models
jarvis --check-fcc
jarvis
```
O comando `--check-fcc` faz três verificações: saúde do servidor, modelos retornados pela API e **geração real** da resposta para a mensagem "Responda somente: OK". Essa última operação utiliza os créditos/quota do provedor selecionado. `--health` isoladamente não comprova inferência. O failover não contorna credenciais inválidas (HTTP 401/403) nem garante que um modelo do catálogo esteja utilizável; ele só confirma um modelo quando responde de verdade.

O FCC pode oferecer seus próprios `MODEL_FALLBACKS`, em sua configuração. A camada do JARVIS complementa esse mecanismo, mudando o **ID requisitado pelo cliente** quando necessário. Evite listar modelos caros caso não queira consumir créditos ao alternar.

## Etapa 5 — diagnóstico e integração inicial com Wayland

Acesse a sessão GNOME/Wayland e instale as dependências opcionais:
```bash
sudo apt install -y xdg-desktop-portal xdg-desktop-portal-gnome libgtk-3-bin
pip install -e '.[desktop]'
```
O pacote `xdg-desktop-portal-gnome` é específico do GNOME; para KDE, use o backend correspondente da sua distribuição. A JARVIS oferece:
- `desktop_info`: informa sessão gráfica, desktop e disponibilidade dos portais;
- `desktop_screenshot`: solicita uma captura pela interface `org.freedesktop.portal.Screenshot`, com **confirmação no terminal e no diálogo do sistema**. O arquivo PNG é salvo em `jarvis_desktop_screenshot.png` no workspace e **não é enviado automaticamente à IA**;
- `desktop_open_app`: abre por `gtk-launch` apenas aplicativos cujos IDs estejam em `JARVIS_ALLOWED_APPS`, sempre com confirmação.

Exemplo:
```bash
export JARVIS_ALLOWED_APPS='org.gnome.Nautilus,firefox'
jarvis
```
Utilize o ID .desktop realmente instalado no seu sistema (por exemplo, confirme com `ls /usr/share/applications`). Essas ações são implementações iniciais: não controlam o mouse ou teclado do desktop. Isso requer uma sessão `RemoteDesktop` autorizada pelo compositor e será integrado após validação específica no GNOME/Wayland.

**Segurança e limitações:** a API Wayland será usada somente com consentimento explícito; não há acesso via `/dev/uinput`, `sudo` ou bypass de permissões. Screenshots podem conter informações privadas; mantenha o workspace protegido. A captura real depende da implementação do portal no seu Linux, ainda não testada nesse desktop. Testes do CI apenas simulam respostas do portal.

### Diagnóstico do Wayland independentemente do FCC

```bash
jarvis --desktop-info
jarvis --desktop-screenshot
```

O primeiro imprime o compositor e os portais detectados; o segundo pede confirmação e abre o diálogo de captura de tela do GNOME/KDE. Execute esses comandos dentro da sessão gráfica do seu Ubuntu, e não via SSH sem encaminhamento DBus/desktop.
