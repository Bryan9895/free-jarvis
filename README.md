# JARVIS FCC — assistente local para Ubuntu GNOME

Assistente pessoal modular em Python conectado ao **Free Claude Code (FCC)** pela API Responses. Oferece chat, execução supervisionada de arquivos, abertura de apps e projetos no VS Code, planejamento persistente, verificações de arquivos e observação de janelas no GNOME Wayland.

**Comece por este guia.** As notas detalhadas e experimentais permanecem ao final deste README. O [registro de continuidade](docs/RETOMADA.md) documenta exatamente onde paramos e o próximo objetivo.

## Instalação rápida no Ubuntu GNOME Wayland

### 1. Pré-requisitos do sistema

Abra um terminal no notebook Ubuntu e instale as dependências básicas:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip python3-pyatspi at-spi2-core libgtk-3-bin
```

O `python3-pyatspi` é usado pelo **Python do sistema**, não pelo Python da `.venv`. O comando `gtk-launch` é usado para abrir aplicativos. O VS Code precisa estar instalado separadamente e ter o comando `code` no PATH caso você queira abrir projetos/arquivos pelo editor. Para conferir: `command -v code`.

### 2. Baixar a JARVIS e instalar o ambiente Python

Para uma instalação nova, use HTTPS (não precisa configurar chave SSH):

```bash
git clone https://github.com/Bryan9895/free-jarvis.git
cd free-jarvis
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[desktop]'
```

Se você já tem o projeto, **não clone novamente**:

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull --ff-only origin main
source .venv/bin/activate
python -m pip install -e '.[desktop]'
```

O módulo de voz, a visão por IA e o navegador automatizado são opcionais. Se quiser preparar também essas capacidades:

```bash
python -m pip install -e '.[browser,desktop,vision]'
python -m playwright install chromium
```

Para voz (ainda experimental), `sudo apt install -y libportaudio2 alsa-utils` e `python -m pip install -e '.[voice]'`. Consulte as notas históricas abaixo para detalhes de modelos de voz, permissões e testes. Não é preciso instalar esses extras para a conversa normal ou o reconhecimento de janelas por GNOME Shell.

Confirme a instalação **da versão deste repositório**:

```bash
jarvis-fcc --doctor
jarvis-fcc --help
```

### 3. Iniciar o servidor FCC (é um serviço separado)

A JARVIS **não inclui** o Free Claude Code, credenciais de provedor nem um modelo de IA. Instale e configure o [Free Claude Code](https://github.com/Alishahryar1/free-claude-code) conforme seu projeto oficial. Inicie o servidor `fcc-server` em **outro terminal** e configure um provedor/modelo com suporte ao endpoint Responses e chamadas de ferramentas. O endereço utilizado nos testes foi `http://127.0.0.1:8082`; ajuste conforme sua instalação.

Na sessão da JARVIS, depois de ativar `.venv`:

```bash
export FCC_URL="http://127.0.0.1:8082"
jarvis-fcc --health
jarvis-fcc --models
```

Para escolher um modelo, **use um ID listado** por `--models`:

```bash
# Exemplo que funcionou em um notebook; pode não estar disponível na sua conta:
export FCC_MODEL="openai/gpt-5.6-luna"
jarvis-fcc --check-fcc
```

Se preferir o modelo padrão anunciado pelo FCC: `unset FCC_MODEL`. `--check-fcc` executa inferência real e pode consumir cota. Caso seu FCC precise de token, defina `FCC_TOKEN` **apenas no seu ambiente local**, nunca no Git.

### 4. Autorizar pastas do notebook e usar o VS Code

O workspace padrão é **`$HOME/Projetos`**, independentemente de onde o repositório foi clonado. Configure explicitamente os diretórios que deseja autorizar:

```bash
mkdir -p "$HOME/Projetos"
export JARVIS_WORKSPACE="$HOME/Projetos"
export JARVIS_ALLOWED_DIRS="$HOME/Documentos:$HOME/Downloads"
```

`JARVIS_ALLOWED_DIRS` usa `:` entre pastas e aceita apenas diretórios existentes. Pedidos relativos à pasta do projeto são resolvidos no workspace; para `Downloads` ou `Documentos`, a JARVIS pode usar **caminhos absolutos**, desde que estejam autorizados. **Nunca autorize a pasta home inteira ou diretórios do sistema para tentar ganhar acesso irrestrito.** Alterações locais continuam exigindo confirmação digitando `SIM`.

O VS Code é opcional. Caso ele esteja instalado, valide `command -v code` para abrir arquivos/projetos diretamente. A JARVIS consegue abrir aplicativos do menu GNOME via `gtk-launch` mesmo que o VS Code não esteja instalado.

### 5. Reconhecimento de janelas no GNOME Wayland

O inventário confiável para aplicativos GNOME que testamos usa a extensão opcional **[Window Calls Extended](https://extensions.gnome.org/extension/4974/window-calls-extended/)**. Verifique se ela é compatível com sua versão (`gnome-shell --version`); **instale e habilite manualmente** no GNOME Extensions.

```bash
gnome-extensions info window-calls-extended@hseliger.eu
jarvis-fcc --windows-diagnostic
```

Resultado esperado depois de habilitar a extensão:

```json
{"status": "observed", "source": "gnome_shell_extension", "complete": false}
```

Se aparecer `source: atspi_accessibility_partial`, a extensão não respondeu e a JARVIS voltou ao mecanismo de acessibilidade, que não lista todas as janelas. Consulte `fallback_reason` e `extension_diagnostic`. O campo `complete: false` significa que **nem a integração com o GNOME Shell garante todas as superfícies**. A observação de uma janela não comprova qual arquivo está ativo.

### 6. Iniciar e testar

Com **FCC ativo**, `.venv` ativa e as variáveis acima configuradas:

```bash
jarvis-fcc
```

Pedidos para testar: "Jarvis, quais janelas estão abertas?", "Jarvis, crie a pasta TesteJarvis dentro de Downloads, salve main.py com print('hello world') e abra no VS Code" e "Jarvis, mostre os programas que você iniciou nesta sessão".

Comandos úteis no chat: `/modelos`, `/modelo atual`, `/acoes`, `/normal`, `/planejar OBJETIVO`, `/plano`, `/historico-planos`, `/metricas`. Para encerrar, digite `sair` ou pressione Ctrl+C (Ctrl+Z apenas suspende o processo).

Diagnóstico sem FCC: `jarvis-fcc --doctor`, `jarvis-fcc --desktop-info`, `jarvis-fcc --windows-diagnostic`. Diagnóstico com FCC: `jarvis-fcc --health`, `jarvis-fcc --models`, `jarvis-fcc --check-fcc`.

### 7. Atualizações e testes

```bash
cd free-jarvis   # ou o caminho onde você clonou o projeto
git pull --ff-only origin main
source .venv/bin/activate
python -m pip install -e '.[desktop]'
PYTHONPATH=src python -m unittest discover -s tests -v
```

O histórico SQLite e as configurações locais não são transferidos pelo Git. **Não** envie tokens, banco de histórico, prints de tela ou arquivos de trabalho ao GitHub. Os testes do GitHub Actions não abrem janelas no seu notebook nem acessam seu FCC; o funcionamento GNOME/FCC real deve ser validado localmente.

### Segurança e limites

As ferramentas respeitam o workspace e pastas explicitamente autorizadas. Arquivos são gravados após confirmação; remoção é recuperável na lixeira interna. O agente não possui shell arbitrário, `sudo` nem controle total do GNOME. Verificações de escrita usam hash SHA-256; a presença/alteração de título de janela é evidência limitada e **não comprova a conclusão de uma ação no aplicativo**. Clique/teclado via RemoteDesktop são experimentais e ficam desabilitados por padrão (não habilite `JARVIS_ENABLE_DESKTOP_INPUT` sem uma sessão de testes supervisionada).

**Amanhã:** continuar a partir do [ponto de retomada](docs/RETOMADA.md): verificar a correlação antes/depois no GNOME real e estudar foco/seleção de janelas por identificador, com aprovação e verificação posterior.

---

## Histórico de implementação e experimentos

Abaixo estão as notas das etapas anteriores, preservadas para consulta. O guia acima é a referência recomendada para instalação nova.

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

## Correções após teste em GNOME/Ubuntu (2026-10-21)

O teste real identificou que FCC `/v1/responses` **só aceita streaming**. A JARVIS agora força `stream=true`, processa o SSE e utiliza o objeto final de `response.completed` para o agente, inclusive quando o modelo pede chamadas de ferramentas.

O teste também encontrou incompatibilidade na introspecção de propriedades do GNOME com `dbus-next` (`power-saver-enabled`). A captura de tela foi alterada para chamadas D-Bus diretas às interfaces Screenshot e Request, **sem introspecção das propriedades do desktop**.

`jarvis-fcc --models` agora apresenta somente IDs e modelo padrão, em vez de todo o JSON de metadados. As aprovações aceitam `sim` ou `SIM`.

Para testar após atualizar:
```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
unset FCC_MODEL
jarvis-fcc --check-fcc
jarvis-fcc --desktop-screenshot
```

O teste de streaming HTTP contra o servidor simulado passou no CI; confirmação do modelo/provedor real e do portal de captura em GNOME ainda depende de teste no computador. O portal solicita confirmação do usuário; não houve tentativa de contornar permissões.

## Validação real GNOME e problema NVIDIA NIM (outubro de 2026)

O teste `jarvis-fcc --desktop-screenshot` foi confirmado **funcionando no GNOME/Wayland** do usuário. A imagem é gerada no workspace mediante autorização. Essa confirmação diz respeito a capturas, não ao controle de teclado e mouse.

O erro `HTTP 404 em /v1/responses` com texto **"Upstream provider NIM returned HTTP 404"** e **"Category: upstream"** indica um erro da rota do fornecedor NIM, não do servidor HTTP local. Agora o failover tenta outro modelo listado no catálogo **somente para essa classe de 404**; um 404 comum continua sendo erro fatal. O teste automatizado cobre essa distinção, mas o resultado real depende de haver outro provedor funcional no FCC.

Teste com prioridade manual em caso de falha de provedores:
```bash
git pull origin main
unset FCC_MODEL
jarvis-fcc --check-fcc
```
Caso queira evitar o modelo NIM primeiro, configure um modelo da lista obtida com `jarvis-fcc --models`, como `openai/gpt-6-luna` **apenas se tiver autorização e desejar usar esse provedor**. Fallback pode enviar prompts a outro provedor e consumir cota.

### Experimento controlado de RemoteDesktop no GNOME/Wayland

A próxima etapa da integração gráfica tem um teste separado, **não ligado ao agente de IA**:
```bash
jarvis-fcc --desktop-remote-test
```
O comando solicita duas permissões: confirmação no terminal e diálogo do GNOME para um dispositivo ponteiro. Se ambos forem aceitos, tenta mover o cursor **25 pixels para a direita**, informa `sent_unverified` (envio não implica movimento confirmado) e **fecha a sessão imediatamente**. Nenhuma tecla ou clique é enviado. O teste não ativa uma sessão persistente e não obtém direitos de superusuário.

O controle gráfico pleno, captura contínua PipeWire, sessão EIS/libei e interpretação visual ainda não foram implementados. Teste o experimento somente na sua sessão gráfica pessoal, sem tarefas sensíveis abertas. Em caso de erro, copie a saída para diagnosticarmos.

### FCC: erro Gemini Interactions API e continuidade automática

Em alguns modelos Gemini, o FCC pode responder `HTTP 400` com `This model only supports Interactions API`. Isso significa que aquele **modelo/rota** não atende ao contrato `/v1/responses`; não significa que o servidor local inteiro esteja inoperante. A JARVIS agora trata **somente essa assinatura específica** como incompatibilidade de modelo e tenta outro anunciado pelo FCC. Um `400` comum continua interrompendo a requisição.

```bash
git pull origin main
unset FCC_MODEL
jarvis-fcc --check-fcc
```

**Nota de privacidade e custos:** modelos diferentes podem usar provedores remotos distintos; não execute o teste com conteúdo sensível. Para determinar os próximos provedores, use `jarvis-fcc --models`; configure explicitamente `FCC_FALLBACK_MODELS` quando precisar de prioridade previsível. O teste usa uma mensagem curta, mas pode consumir cota.

**Wayland:** `jarvis-fcc --desktop-remote-test` retornou `sent_unverified` em sessão GNOME real, demonstrando que a solicitação e o envio do evento não falharam. A confirmação visual de deslocamento do cursor ainda não foi reportada.

### Diagnóstico de lentidão no FCC e cursor não observado — 21/10/2026

Um usuário interrompeu `jarvis-fcc --check-fcc` com Ctrl+C após aguardar uma resposta do servidor HTTP; isso gerou `KeyboardInterrupt` enquanto a leitura da resposta upstream estava pendente. Não implica necessariamente bug no cliente: algum modelo/provedor estava demorando para responder. O diagnóstico foi limitado a **três modelos** e timeout de **15 segundos por leitura HTTP** e agora mostra os modelos em teste no stderr. O timeout vale por operação de leitura de rede e **não é um limite global rígido de execução**.

No GNOME, o diálogo RemoteDesktop inclui uma chave **"Permitir interação remota"**; ela precisa estar habilitada e a sessão autorizada através do botão **Compartilhar**. Mesmo assim, o retorno `sent_unverified` só comprova que o evento foi submetido pelo D-Bus, não que o cursor se moveu. O experimento agora espera o diálogo desaparecer, envia **3 movimentos de 25 pixels**, dá tempo para o compositor processá-los e encerra a sessão. Nenhum clique ou digitação é enviado.

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
unset FCC_MODEL
jarvis-fcc --check-fcc
jarvis-fcc --desktop-remote-test
```

Para evitar esperar por provedores remotos no diagnóstico, selecione explicitamente um modelo local anunciado pelo FCC, por exemplo `export FCC_MODEL='ollama/qwen3.5:2b'` **se disponível e carregado no Ollama**; confirmar um modelo listado não basta para garantir que sua inferência funcione.

### Modelo local Ollama: timeout e política de troca (21/10/2026)

Em teste real, `ollama/qwen3.5:2b` excedeu o timeout anterior de 15 segundos do JARVIS FCC. Em seguida, o sistema tentou modelos Gemini que exigem uma rota diferente (Interactions API). Isso **não prova** que o Qwen não funciona: um modelo carregado a frio pode demorar e a resposta da integração local ainda precisa ser confirmada.

Agora, com `FCC_MODEL` explicitamente selecionado, a JARVIS **não tenta outros modelos automaticamente**; ela usa somente `FCC_FALLBACK_MODELS` declarados pelo usuário. Sem `FCC_MODEL`, pode tentar outros modelos anunciados **do mesmo provedor**. Para autorizar descoberta entre provedores, configure `FCC_ALLOW_CROSS_PROVIDER=1` (cuidado com privacidade e cobranças).

O diagnóstico usa timeout de 120 segundos para um modelo `ollama/` escolhido e 30 segundos para os demais. É possível ajustar:

```bash
export FCC_MODEL='ollama/qwen3.5:2b'
unset FCC_FALLBACK_MODELS
unset FCC_ALLOW_CROSS_PROVIDER
export FCC_DIAGNOSTIC_TIMEOUT=120
jarvis-fcc --check-fcc
```

Para testar diretamente o mecanismo local antes de usar o FCC:

```bash
ollama list
ollama ps
ollama run qwen3.5:2b "Responda apenas OK"
```

Se a execução direta do Ollama funcionar, mas `jarvis-fcc --check-fcc` não, o problema é provavelmente na integração/servidor FCC, e não necessariamente nos pesos do modelo. Se ambos falharem, investigue Ollama, carregamento do modelo e recursos disponíveis. Evite iniciar múltiplas gerações simultâneas em um computador com RAM limitada.

**Wayland validado em dispositivo real:** o usuário confirmou que o movimento do ponteiro funcionou após autorizar interação remota no GNOME. Não foram testados ainda cliques nem digitação via portal.

### Qwen via FCC retornando response.incomplete

Em teste real, o Ollama respondeu normalmente com `qwen3.5:2b`, mas a JARVIS recebeu `response.incomplete` do FCC. No diagnóstico anterior, o limite era apenas **48 tokens** e o modelo consumiu parte desse limite em seu raciocínio. O endpoint FCC aceita `max_output_tokens` e `reasoning`; o diagnóstico foi ajustado para `max_output_tokens=768` e `reasoning={"effort":"none"}`. Esta opção tenta reduzir o raciocínio, mas o provedor/modelo pode não obedecê-la. Falhas `response.incomplete` agora mostram a razão sem imprimir todo o conteúdo de raciocínio.

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
export FCC_MODEL='ollama/qwen3.5:2b'
unset FCC_FALLBACK_MODELS FCC_ALLOW_CROSS_PROVIDER
jarvis-fcc --check-fcc
```

Se persistir `response.incomplete`, será necessário inspecionar a razão devolvida pelo FCC e o mapeamento do seu modelo, não assumir que a conexão HTTP falhou. O teste automatizado exercita as condições de saída, mas a confirmação com seu Ollama/FCC permanece necessária.

### Etapa 5: testes de clique e teclado no GNOME/Wayland

Os testes de movimento do ponteiro e de captura de tela já foram **confirmados no Ubuntu GNOME do usuário**. Esta entrega acrescenta dois testes novos, independentes do FCC e **não disponíveis como ações autônomas da IA**. Consulte o padrão [XDG RemoteDesktop Portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html) para as permissões e interfaces.

**Teste de clique:**
1. Antes de executar, posicione o cursor numa área vazia da área de trabalho, sem botões, links, janelas com conteúdo sensível ou ações que possam alterar arquivos.
2. Execute `jarvis-fcc --desktop-click-test`.
3. Digite `sim`; habilite *Permitir interação remota* e selecione *Compartilhar* na janela GNOME.
4. O teste enviará um único clique esquerdo no local do cursor após o diálogo sair da tela. Ele devolve `sent_unverified`, que não prova efeito visual.

**Teste do teclado:**
1. Abra um editor de texto com documento **vazio**, por exemplo Gedit/GNOME Text Editor. Não use terminal nem campos que possam executar comandos.
2. Execute `jarvis-fcc --desktop-keyboard-test` em outro terminal, mantendo o editor preparado para receber foco depois da autorização.
3. Digite `sim`, habilite *Permitir interação remota* e clique em *Compartilhar* no diálogo GNOME.
4. O teste enviará **uma única letra minúscula `j`** ao aplicativo atualmente focado. Se o editor não receber a letra, o foco pode ter ficado na janela do terminal.
5. Feche o documento sem salvar e informe se a letra apareceu.

A autorização de teclado e a de ponteiro são solicitadas **separadamente**, nunca juntas. As ações enviam pares pressionar/liberar usando `NotifyPointerButton` ou `NotifyKeyboardKeysym`, sem bypass de Wayland. O campo `status=sent_unverified` indica apenas que a chamada D-Bus foi aceita; a confirmação visual depende do usuário. **Não execute esses testes sobre interfaces que façam compras, exclusões, envios ou outras ações irreversíveis.**

A automação de cliques e digitação a partir de comandos de linguagem natural continua bloqueada até validarmos os testes físicos e adicionarmos salvaguardas e verificação do contexto visual.

### Integração experimental de ações do desktop solicitadas pelo agente

Após a validação física de captura, movimento, clique esquerdo e entrada simples de teclado no GNOME/Wayland, foi adicionada a ferramenta `desktop_input` para o agente de IA. Ela **não é oferecida ao modelo por padrão**. Para habilitar explicitamente em uma sessão de teste:

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
source .venv/bin/activate
export FCC_MODEL="ollama/qwen3.5:2b"
export JARVIS_ENABLE_DESKTOP_INPUT=1
jarvis-fcc
```

Teste com um aplicativo de texto vazio ou área de trabalho sem ações sensíveis. Peça, por exemplo, **"Solicite a ferramenta desktop_input para mover o ponteiro 20 pixels para a direita"**. O modelo não observa sua tela nem conhece a posição real do cursor, portanto a instrução humana é essencial. Cada solicitação exige uma confirmação no terminal e a autorização de controle remoto do GNOME; a sessão D-Bus encerra ao terminar a ação. Exemplos de operações possíveis: `move` (deslocamento relativo de no máximo 50 pixels por eixo), `click` (um clique esquerdo onde o cursor estiver) e `type` (no máximo 40 caracteres, apenas `a-z`, `0-9` e espaços, sem atalhos nem Enter).

**Limites e privacidade:** confirmação `SIM` pode autorizar um clique com efeitos reais, como excluir um arquivo ou confirmar uma ação; por isso mantenha janelas sensíveis fechadas. O recurso não verifica foco da janela nem conteúdo da tela, não envia capturas ao modelo e não deve ser usado para fluxos irreversíveis. Mesmo que o retorno indique `sent_unverified`, confirme o resultado visualmente. **Para desativar novamente**, interrompa o chat e execute `unset JARVIS_ENABLE_DESKTOP_INPUT`. Não use `sudo`, uinput ou mecanismos de bypass do portal. Não há controle persistente ou automatização ilimitada; cada chamada solicita autorização novamente.

A documentação e os testes confirmam as proteções de software. **A integração completa entre FCC, ferramenta e entrada desktop solicitada pelo modelo precisa de validação física no GNOME**.

### Etapa 5: descrever e diagnosticar a tela (visão experimental)

Após o teste bem-sucedido de ações gráficas enviadas pela IA, a JARVIS passou a aceitar **análise visual pontual**, separada do controle do mouse. O FCC aceita `input_image` no formato Responses; o modelo Ollama configurado **também precisa oferecer visão**. Ter Qwen funcionando para texto não comprova suporte à imagem.

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
source .venv/bin/activate
python -m pip install -e '.[desktop,vision]'
export FCC_MODEL='ollama/qwen3.5:2b'
jarvis-fcc --see-screen "Descreva o que aparece nesta tela sem executar ações."
```

Dentro de uma sessão `jarvis-fcc`, o comando especial `/tela` (ou `/tela Por que esta janela mostra um erro?`) executa o mesmo procedimento. A descrição é mostrada no terminal, **sem ser adicionada automaticamente ao histórico de conversa**.

**Permissões:** primeiro, a JARVIS pede captura e o GNOME exibe seu diálogo. Depois, comprime a imagem em JPEG de no máximo 1280×900 e solicita uma **segunda aprovação antes de enviá-la**. O comando chama o cliente FCC diretamente, com **modelo fixo, sem failover e sem ferramentas**, para evitar mudanças de provedores e cliques automáticos durante a observação. A imagem original salva no workspace permanece em `jarvis_desktop_screenshot.png`: mantenha esse diretório protegido, apague quando não precisar e feche janelas sensíveis antes de capturar.

Por padrão, somente IDs `ollama/` são aceitos. Se seu FCC estiver apontando Ollama para um servidor remoto, os dados ainda podem deixar a máquina: verifique sua configuração. Para analisar usando outro provedor, seria necessário habilitar explicitamente `JARVIS_ALLOW_REMOTE_VISION=1`; isso pode enviar o conteúdo da tela a terceiros e consumir cota. Não recomendamos enquanto houver documentos, mensagens, credenciais ou dados privados visíveis.

**Limitações:** não há captura contínua, detecção de alvo clicável, coordenadas inferidas automaticamente nem execução de ações com base em observações. O modelo pode interpretar imagens incorretamente. Se o Qwen 3.5 2B não aceitar `input_image` via FCC, o comando informa erro; será preciso investigar o suporte visual específico da combinação modelo/provedor, não assumir que o recurso funciona.

### Clique guiado por visão — etapa supervisionada

Após validação da visão do Qwen 3.5 2B via FCC, foi implementado um experimento para **observar → propor → posicionar manualmente → autorizar clique → observar novamente → comparar**.

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
source .venv/bin/activate
python -m pip install -e '.[desktop,vision]'
export FCC_MODEL='ollama/qwen3.5:2b'
jarvis-fcc --guided-click "Selecione uma área vazia da janela de teste"
```

Também disponível dentro do chat via `/clicar-guiado <descrição do alvo>`.

O fluxo usa SOMENTE `ollama/` explicitamente escolhido; captura a tela com confirmação do terminal e GNOME, pede aprovação de envio ao modelo, apresenta a explicação visual (pode alucinar), então **o usuário posiciona o cursor manualmente**, confirma `CLICAR`, autoriza o clique e o portal GNOME. Uma captura posterior e o envio de duas imagens para comparação são opcionais e exigem novas aprovações. O modelo apenas avalia diferenças visíveis; o resultado continua `sent_unverified`, nunca `success` automático.

**Use somente em uma janela descartável com área vazia ou aplicativo de demonstração**, nunca em botões que enviam mensagens, compram, apagam, instalam ou alteram arquivos. A IA ainda não conhece coordenadas reais do mouse, nem tem validação robusta para operar sozinha. Este experimento é separadamente acionado, não acrescenta ferramentas autônomas ao agente e não executa passos encadeados sem autorização.

### Localização de alvos visuais com imagem anotada (experimental)

A JARVIS pode receber uma meta visual e solicitar ao Qwen uma região **normalizada de 0 a 1000**. O retorno da IA deve ser JSON válido e a área precisa ser geometricamente consistente. A JARVIS cria uma cópia da captura com retângulo vermelho e centro amarelo, permitindo **inspeção humana antes de qualquer clique**.

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
source .venv/bin/activate
python -m pip install -e '.[desktop,vision]'
export FCC_MODEL='ollama/qwen3.5:2b'
jarvis-fcc --locate-target "Ícone do gerenciador de arquivos"
```

Dentro do chat, use `/localizar Ícone do gerenciador de arquivos`. Após as autorizações de captura e envio ao Ollama, abra `~/Projetos/jarvis_target_preview.png` para conferir a sugestão. O modelo pode errar a região, especialmente em interfaces compactas, escalonadas ou em múltiplos monitores. O status `proposal_only` **não representa identificação validada**. Se `found=false` ou os dados forem inválidos, a ação é interrompida.

**Nenhum clique, digitação, movimento do cursor ou execução de comandos ocorre nesse modo.** Não habilita automação coordenada e não assume que o modelo sabe a posição real do mouse. A próxima integração precisará da API de movimento absoluto vinculada a uma stream ScreenCast e de confirmação humana de alvo, antes de enviar qualquer evento.

### Correção do `--locate-target` com Qwen 3.5 (response.incomplete)

Um teste real do localizador visual em `ollama/qwen3.5:2b` retornou `response.incomplete` com `reason=max_output_tokens`. A captura e o envio da imagem foram autorizados, mas o modelo não finalizou a resposta no orçamento anterior de 1.200 tokens.

O localizador agora usa `reasoning={"effort":"none"}` e `max_output_tokens=2048`. Se (e somente se) a saída terminar com esse erro de limite, o mesmo modelo recebe **uma segunda tentativa** com `max_output_tokens=4096`; nenhuma outra captura ou novo provedor é iniciado. A confirmação de envio informa que podem ocorrer até duas tentativas. O Qwen/FCC pode ignorar `reasoning.effort`; por isso, mesmo com essa correção, ainda é possível receber uma resposta incompleta ou um JSON inválido. Isso não executa nenhum clique.

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
export FCC_MODEL='ollama/qwen3.5:2b'
jarvis-fcc --locate-target 'Ícone do gerenciador de arquivos'
```

Se continuar incompleto após duas tentativas, não repita indefinidamente: será necessário mudar a configuração de raciocínio para esse modelo no FCC ou usar um modelo visual mais adequado ao posicionamento espacial. Uma descrição de tela bem-sucedida **não garante** que o modelo seja capaz de devolver caixas delimitadoras corretas.

### Qwen retornou texto, mas não JSON no localizador

Se `--locate-target` responder `A IA não retornou JSON de localização válido`, significa que **a inferência completou**, mas o conteúdo não obedeceu ao contrato de coordenadas. Isso é diferente do erro anterior `response.incomplete`.

O localizador agora extrai **um único objeto JSON completo** mesmo que apareça em bloco Markdown ou venha precedido/seguido de explicação. A validação de `bbox`, limites, `found` e `confidence` permanece obrigatória. Se não houver um objeto inequívoco, retorna `status=unstructured`, `action_executed=false` e um trecho limitado da saída (`model_excerpt`) para diagnóstico. Isso não cria uma região fictícia nem tenta clicar.

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
export FCC_MODEL='ollama/qwen3.5:2b'
jarvis-fcc --locate-target 'Ícone do gerenciador de arquivos'
```

Caso receba `unstructured`, compartilhe `model_excerpt` **após verificar que não contém dados privados**. Um modelo que descreve bem a tela pode não conseguir estimar caixas espaciais confiáveis. A pré-visualização só é gerada quando `found=true` e a caixa está formalmente válida; ainda será necessária conferência humana.

### Seleção dinâmica de modelos do FCC (inspirada no sistema modular do Mark-LVI)

O chat da JARVIS agora permite usar **qualquer ID anunciado** em `/v1/models?view=responses`, sem reiniciar o processo:

```text
/modelos                  # lista modelos expostos no FCC
/modelo atual             # mostra o selecionado
/modelo ollama/qwen3.5:4b # troca explicitamente para qualquer ID listado
/modelo auto              # volta ao modelo padrão e fallback configurado
/modelo todos             # considera todo o catálogo como possíveis fallbacks
```

O modelo de `/tela`, `/localizar` e `/clicar-guiado` segue a seleção atual no chat, mas esses comandos podem recusar modelos sem visão ou fora da política local. A lista do FCC **não prova** que o modelo está operacional ou que suporta function calling, `input_image` ou a rota Responses. `/modelo todos` só tenta outro modelo diante de erros de fallback reconhecidos: um erro permanente de protocolo, permissão ou argumentos ainda interrompe a execução. Como o catálogo pode conter modelos remotos, esse comando pode encaminhar o texto enviado ao modelo a outro provedor; não use com dados privados se não confia nesses provedores.

**Controle do computador:** nesta versão, a JARVIS continua usando autorização por ação e os diálogos nativos RemoteDesktop/Screenshot do GNOME. A seleção de modelos não altera as permissões de execução. Uma sessão de controle não deve contornar permissões do sistema operacional.

### Desempenho: respostas rápidas e executor revisado (outubro de 2026)

O agente anteriormente enviava 14 ferramentas para **toda** pergunta, inclusive perguntas como `O que é Python?`, sem configurar o esforço de raciocínio nem um limite de saída. Modelos pequenos com geração de raciocínio (como Qwen 3.5 2B) podem gastar muito tempo antes de mostrar a resposta.

A implementação atual adota um roteador local conservador, que **não chama outro modelo** para classificar. Perguntas curtas puramente informativas passam por um turno sem ferramentas, com até 4 mensagens recentes, `reasoning={"effort":"none"}` e `max_output_tokens=512`. Pedidos de ações/desktop/arquivos/navegador continuam no modo de ferramentas, com contexto usual, orçamento de 1536 tokens e até seis rodadas de execução. O executor evita executar a **mesma ferramenta com os mesmos argumentos mais de uma vez dentro do turno**, reutilizando o resultado anterior (mecanismo inspirado no pipeline do Mark-LVI). Em nenhum caso isso significa que uma ação tenha sido verificada no sistema operacional.

Comandos no chat:
- `/rapido`: força respostas sem ferramentas; não use para pedidos de ações.
- `/normal`: restaura seleção automática (padrão).
- `/acoes`: oferece ferramentas mesmo para perguntas simples.
- `/metricas`: mostra duração total da última resposta, tempo de cada geração FCC, quantidade de chamadas de ferramenta e rota escolhida.

Para exibir a métrica após **toda** resposta, configure `export JARVIS_SHOW_TIMING=1` antes de executar `jarvis-fcc`.

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
source .venv/bin/activate
export FCC_MODEL="ollama/qwen3.5:2b"
export JARVIS_SHOW_TIMING=1
jarvis-fcc
# Dentro do chat:
# O que é Python?
# /metricas
# /acoes
# Liste os arquivos do workspace
# /normal
```

**Como interpretar:** se `model_s` já for alto mesmo com zero ferramentas, a lentidão está sobretudo na geração pelo modelo/provedor, no carregamento do Ollama ou no hardware; não é causada por chamadas de ferramentas. Compare a primeira pergunta (carregamento a frio) com a segunda, de comprimento equivalente. Em outro terminal, use `ollama ps` para ver se o modelo está carregado e se executa em CPU/GPU. O comando `ollama run qwen3.5:2b "Responda só OK"` serve como comparação sem FCC. Um modelo maior não é necessariamente mais rápido em um notebook com 8 GB de RAM.

A seleção de todos os modelos FCC permanece disponível, mas nenhum ajuste garante que um modelo externo seja mais rápido ou compatível com ferramentas. O modo rápido não recebe ferramentas, então não pode executar ações. O roteador faz classificação simples e pode errar; `/acoes` força a rota de ferramentas, sem eliminar aprovações e permissões nativas.

### Planejador multietapas supervisionado — próxima fase após otimização do tempo de resposta

A JARVIS agora pode pedir ao modelo FCC um **plano de até cinco etapas** e apresentá-lo para inspeção **sem executar ferramentas enquanto planeja**. O planejador aceita somente um objeto JSON com lista de etapas curtas. O usuário decide se deseja executar o plano; operações que já exigiam autorização (desktop, escrita, navegador) continuam exigindo as permissões anteriores. O GNOME Wayland continua controlando os diálogos do portal.

Comandos dentro de `jarvis-fcc`:

```text
/planejar Liste os arquivos Python do meu projeto e resuma o conteúdo deles
/plano
/executar-plano
/cancelar-plano
```

Durante a execução, cada etapa é enviada ao agente existente no modo `tools`, que registra duração, evita repetir chamadas idênticas no turno e detecta recusas e falhas reportadas por ferramentas. Se o agente registrar erro ou recusa de ferramenta, a execução para e as próximas etapas ficam pendentes. **O planejamento não amplia o conjunto de ferramentas nem contorna permissões.** O plano não é persistido entre reinicializações.

Estados do plano: `ready`, `running`, `completed_unverified`, `stopped`, `cancelled`. Estados das etapas incluem `pending`, `reported_unverified`, `blocked`, `failed`. Uma conclusão narrada pelo modelo nunca conta como confirmação externa do resultado; essa etapa ainda precisará de verificadores de estado independentes.

O planejamento acrescenta uma inferência antes das etapas, então é destinado a **tarefas com várias ações**, não a perguntas simples. Para perguntas, mantenha `/normal` ou `/rapido`. Na sessão atual, a rota rápida com `openai/gpt-5.6-luna` foi medida pelo usuário em cerca de 2,4 a 4,0 segundos; não extrapole esses números para Qwen local ou para tarefas com ferramentas.

### Planos persistentes e visualização amigável no terminal

O planejador agora salva tarefas, estados e checkpoints na tabela `task_plans` do SQLite configurado por `JARVIS_DB`. A recuperação ocorre automaticamente quando o chat inicia. Uma execução que estava com estado `running` ao reiniciar é marcada como `interrupted`, sem repetir nenhuma operação, pois não é possível comprovar que a ação anterior terminou.

Os comandos passam a ser:

```text
/planejar Liste os arquivos do workspace e analise a estrutura do projeto
/plano
/historico-planos
/executar-plano
/cancelar-plano
```

`/plano` agora mostra um painel de texto com objetivo, modelo, estado, etapas e barra de progresso em vez de JSON. `/historico-planos` mostra as últimas dez tarefas, mesmo após reiniciar. O painel diferencia explicitamente **etapa processada** de **resultado verificado**; não infere êxito externo com base apenas na resposta do modelo.

O histórico fica em `~/.local/share/jarvis-fcc/memory.sqlite3` por padrão e pode conter objetivos e resultados sensíveis em texto puro. Proteja a conta local e evite armazenar segredos nas tarefas. A retomada automática e a reexecução de etapas interrompidas **não** estão habilitadas: antes de executar novamente, crie um novo plano ou confira manualmente o estado.

### Retomada supervisionada de planos e seleção do histórico

A JARVIS agora permite selecionar planos históricos por ID e continuar **somente etapas pendentes**, sem repetir automaticamente ações concluídas ou incertas. Os novos comandos são:

```text
/historico-planos
/selecionar-plano 12
/plano
/resolver-etapa skip
/retomar-plano
/executar-plano
```

Em vez de `skip`, use `/resolver-etapa retry` para retornar **a primeira etapa incerta** à fila de pendentes. `skip` significa apenas "não executar novamente", **não** indica que a ação anterior teve sucesso. O comando de resolução exige confirmação explícita, e cada ação de ferramenta mantém suas permissões. Se houver várias etapas incertas, resolva uma por comando e confira `/plano` entre elas. Depois use `/retomar-plano` para tornar o plano executável e `/executar-plano` para autorizar a execução apenas do que continua pendente.

Esta versão **não** inicia tarefas em segundo plano, não retoma automaticamente após crash e não verifica por conta própria se um clique ou escrita anterior realmente aconteceu. O plano e suas decisões continuam registrados no SQLite local, inclusive após reiniciar a aplicação. Não escolha `retry` em ações potencialmente irreversíveis sem conferir manualmente o estado do sistema.

### Tarefas por conversa natural (sem comandos)

O chat agora inclui um roteador local de intenções (`task_intent.py`) e um controlador (`natural_tasks.py`) conectados ao planejador SQLite. Não é necessário usar comandos `/` para os casos mais comuns:

- `Jarvis, analise os arquivos Python do meu projeto e depois explique sua organização.` — cria plano, apresenta as etapas e pede autorização para executá-las.
- `Jarvis, planeje uma análise do workspace.` — cria plano, sem executar até receber `Execute o plano`.
- `Como está o meu plano?` — mostra painel de andamento, sem JSON bruto.
- `Mostre o histórico das minhas tarefas.` — mostra tarefas salvas.
- `Continue a análise do meu projeto de onde parou.` — procura tarefa relacionada no histórico. Em caso de dúvida, pede especificação em vez de selecionar arbitrariamente.
- `Ignore a etapa interrompida.` ou `Repita a etapa interrompida.` — registra uma decisão explícita para a **primeira etapa incerta**, mas nunca assume sucesso passado.
- `Continue de onde parou.` — executa somente etapas pendentes **depois** de autorização; etapas incertas precisam de resolução prévia.

O roteamento não faz outra inferência para classificar intenções comuns, preservando a velocidade de perguntas simples. Pedidos que o roteador não reconhecer continuam na conversa normal do agente; ainda não há entendimento semântico completo de todas as paráfrases, nem execução em segundo plano. Alguns objetivos complexos podem requerer reformulação para ativar planejamento. As ferramentas existentes e as autorizações de cada uma permanecem as mesmas. Os comandos explícitos `/plano`, `/planejar` etc. continuam disponíveis como alternativa.

### Operações de arquivos — etapa de controle real do Ubuntu

O agente FCC passa a oferecer três ferramentas novas: `make_directory`, `move_path` e `delete_path`. Elas criam subpastas, renomeiam/movem arquivos e pastas e movem itens para uma **lixeira recuperável** `JARVIS_WORKSPACE/.jarvis-trash`. Não existe exclusão definitiva nesta etapa. Cada ação solicita autorização e fica restrita ao workspace configurado (geralmente `~/Projetos`); não permite mover/remover a raiz nem sobrescrever destinos existentes.

Exemplos em linguagem natural:

```text
Crie uma pasta chamada TesteJarvis dentro do meu workspace.
Renomeie a pasta TesteJarvis para ProjetoTeste.
Mova a pasta ProjetoTeste para a lixeira interna.
```

Para recuperar um item, localize a entrada criada em `.jarvis-trash` e mova-a manualmente para o destino desejado. O navegador de arquivos ou ferramenta `move_path` podem auxiliar nessa recuperação se o destino estiver vazio. Cada ação do modelo requer um provedor FCC que suporte function calling; modelos anunciados mas incompatíveis não executarão as ferramentas.

**Limites atuais:** não existe acesso arbitrário ao computador, execução irrestrita de programas, gerenciamento de pacotes ou exclusão permanente. O GNOME Wayland mantém permissões próprias. A próxima fase de controle do sistema precisará separar descoberta de apps, seleção de diretórios adicionais por autorização e verificação independente dos efeitos.

### Ubuntu: pesquisar aplicativos, executá-los e autorizar pastas adicionais

A JARVIS possui novas ferramentas via FCC:
- `list_installed_apps`: pesquisa nomes e IDs `.desktop` anunciados no menu do GNOME por meio do catálogo XDG local; não executa nada.
- `launch_installed_app`: solicita autorização e abre um aplicativo instalado pelo ID retornado na pesquisa, com `gtk-launch`. Não interpreta nem executa a linha `Exec` de arquivos `.desktop`, não usa shell nem aceita um comando livre. O resultado `launched_unverified` significa que o lançador foi iniciado, não necessariamente que a janela apareceu.
- `authorized_directories`: lista as raízes de arquivos que a JARVIS está autorizada a acessar.

Para permitir que `list_files`, `read_file`, `write_file`, `make_directory`, `move_path` e `delete_path` trabalhem também em diretórios pessoais adicionais, defina `JARVIS_ALLOWED_DIRS` **antes** de abrir a JARVIS. Diretórios informados devem existir; separe com `:`. Caminhos relativos continuam sendo resolvidos no workspace original, enquanto caminhos absolutos dentro das raízes adicionais são aceitos.

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
source .venv/bin/activate
export JARVIS_ALLOWED_DIRS="$HOME/Documentos:$HOME/Downloads"
jarvis-fcc
```

Pedidos naturais de exemplo: `Pesquise os aplicativos instalados com nome Firefox`; `Abra o aplicativo Firefox instalado`; `Liste os arquivos em /home/bryan/Documentos`; `Crie a pasta /home/bryan/Documentos/ProjetoPython`. Para abrir aplicativos por nome, o modelo precisa pesquisar o ID correto antes de invocar o lançador. Usar nomes diferentes no menu pode exigir pesquisar por outro termo.

**Restrições:** não há execução irrestrita de programas/terminal, instalação de pacotes, administração/root, acesso a outras pastas sem configuração ou garantia de foco/abertura da janela. O GTK/GNOME pode exigir permissões adicionais. Exclusão usa a lixeira recuperável do workspace, mesmo para itens movidos de raízes adicionais. Acesso a caminhos simbólicos é recusado para operações mutáveis. Configure somente diretórios que realmente deseja expor aos modelos FCC, especialmente se utilizar provedores remotos.

### Próxima etapa: abrir projetos no editor e acompanhar lançadores

A JARVIS agora fornece ferramentas `create_python_project`, `open_project` e `managed_processes` no catálogo FCC. Isso permite encadear pedidos como:

```text
Jarvis, crie um projeto Python chamado Exemplo dentro de Documentos
Jarvis, abra o projeto Exemplo no VS Code
Jarvis, quais programas você iniciou nesta sessão?
```

`create_python_project` cria uma **pasta nova** com `main.py`, `README.md` e `.gitignore`, sem sobrescrever arquivos, instalar pacotes ou executar scripts. `open_project` aceita `editor="vscode"`, `vscodium` ou `vscode-insiders` e uma pasta existente dentro das raízes autorizadas. Abre diretamente com o executável `code`, `codium` ou `code-insiders` resolvido pelo PATH, usando `subprocess.Popen` com lista de argumentos, **sem shell** e mediante autorização.

`managed_processes` informa o PID, identificador da sessão e estado do **processo lançador** (running/exited), mas não comprova abertura de uma janela nem o estado de programas que reutilizam instâncias já abertas. O registro é válido apenas durante a sessão atual da JARVIS e não inclui processos de outros aplicativos. Encerrar a JARVIS não mata os aplicativos iniciados. Isso evita um comando genérico para terminar processos alheios.

Para utilizar Documentos:

```bash
cd ~/Documentos/Projetos/Jarvis/free-jarvis
git pull origin main
source .venv/bin/activate
export JARVIS_ALLOWED_DIRS="$HOME/Documentos:$HOME/Downloads"
jarvis-fcc
```

Exemplo de caminho absoluto autorizado: `/home/bryan/Documentos/Exemplo`. Para comandos de ferramentas, selecione um modelo FCC compatível com `function_call`. Os estados de lançamento são `launched_unverified` até existir verificação independente. Esta etapa ainda não monitora janelas ou aplicativos iniciados fora da JARVIS.

### Correções a partir dos testes reais do usuário (criar main.py, abrir VS Code)

Os testes mostraram que o modelo podia responder `Posso criar, confirma?` e o planejador marcava uma etapa como processada sem alterações reais. Agora o agente registra `tool_outcomes` com os resultados estruturados de cada ferramenta executada e o planejador interrompe etapas de escrita/abertura se nenhuma ferramenta retornar evidência de operação. Isso **não** substitui uma verificação posterior do estado do sistema; `completed_unverified` continua indicando resultado não verificado independentemente.

Novas ferramentas:
- `open_file(path, editor="vscode")`: abre um **arquivo existente** individual em VS Code (ou alternativas previstas), ao contrário de `open_project` que abre pastas. Retorna `launched_unverified`; não confirma a janela.
- `verify_file(path, content?)`: confirma a existência do arquivo ou compara seu conteúdo textual exato; retorna `verified`, `not_found` ou `content_mismatch` e não escreve nada.

O prompt do agente recomenda `list_files` para buscar caminhos, em vez de tentar `run_command` com argumentos livres. O prompt do planejador distingue pasta do projeto e arquivo interno.

Exemplo, iniciando com `JARVIS_ALLOWED_DIRS="$HOME/Documentos:$HOME/Downloads"`:

```text
Jarvis, crie a pasta TestJarvis em Downloads, crie TestJarvis/main.py
com print("hello world") e abra o arquivo no VS Code.
```

A pasta `$HOME/Downloads/TestJarvis` será criada se estiver ausente, e o arquivo ficará dentro dela. Se faltar permissão ou ferramenta, a etapa deve ser mostrada como bloqueada, não concluída. O prompt sozinho não impede todo erro de interpretação de linguagem natural; confira as etapas exibidas antes de autorizar execução. A JARVIS ainda não tem inspeção de janelas do GNOME para atestar visualmente que o VS Code exibiu o arquivo.

### Verificação independente de resultados por etapa

A JARVIS agora confere automaticamente operações do sistema de arquivos depois que o modelo chama ferramentas: criação de pastas, estrutura de projeto Python, escrita de arquivos, movimentação e envio para a lixeira interna. A verificação de `write_file` compara SHA-256 do conteúdo esperado com os bytes realmente lidos do arquivo. O hash esperado é usado durante a sessão de execução e o conteúdo privado não é exibido nas métricas. A verificação nunca executa comandos shell.

Estados novos de etapa e plano:
- `verified`: a operação de arquivo foi conferida no filesystem;
- `reported_unverified`: ferramenta executada, mas sem verificação independente (por exemplo VS Code e outros lançadores);
- `completed_verified`: todas as etapas do plano foram verificadas;
- `completed_unverified`: houve etapas sem confirmação independente;
- `blocked/stopped`: ocorreu divergência ou falha de verificação.

O painel `/plano` mostra ✓ para efeito verificado e ◇ para execução não verificada. Exemplo de teste: peça para criar uma pasta `TesteVerificacao` em `~/Downloads`, criar um `main.py` dentro dela com `print("hello world")` e depois abrir o arquivo no VS Code. A criação/escrita podem ser verificadas automaticamente; **a janela do VS Code ainda não**. A IA não deve tratar uma saída do lançador como confirmação de que a janela foi aberta.

Limites: verificações são uma fotografia do estado logo após a operação, não garantem que outros processos não alterem o arquivo posteriormente. A abertura de aplicativos e interações com janelas GNOME continuam fora do escopo de verificação independente; esses passos impedem que um plano completo receba `completed_verified`.

### GNOME Wayland: observar janelas abertas (AT-SPI)

Esta etapa adiciona as ferramentas FCC `desktop_windows` e `verify_app_window` para consultar **somente aplicativos e títulos de janelas** expostos pelo serviço de acessibilidade do Ubuntu (AT-SPI). A consulta não move o mouse, não usa X11 e não requer contornar permissões do compositor. Segundo a documentação do Ubuntu, AT-SPI funciona via D-Bus e depende de cada aplicativo publicar objetos acessíveis.

Pré-requisito no Ubuntu:

```bash
sudo apt update
sudo apt install python3-pyatspi at-spi2-core
```

A JARVIS pode continuar rodando dentro de `.venv`: ela usa o `/usr/bin/python3` do sistema apenas para consultar os bindings de acessibilidade em um subprocesso com timeout de 6 segundos. Não reinstale a venv. O GNOME deve estar com os serviços de acessibilidade em funcionamento; aplicativos Electron podem expor informações incompletas.

Pedidos de teste na conversa:

```text
Jarvis, quais janelas do desktop você consegue identificar?
Jarvis, verifique se há uma janela do VS Code aberta.
Jarvis, confira se uma janela do Firefox aparece no GNOME.
```

Respostas possíveis: `window_observed` (janela acessível localizada), `not_observed` (nenhuma correspondência na árvore, **não comprova aplicativo fechado**) e `unavailable` (serviço/biblioteca sem resposta). A ferramenta **não verifica foco, conteúdo ou arquivo ativo**; mesmo quando um título contém `main.py`, isso é apenas uma indicação fornecida pelo aplicativo. Executar um programa continua retornando `launched_unverified`, pois localizar uma janela parecida não demonstra que o processo lançado foi a causa de sua aparição.

Se o comando retornar `unavailable`, execute `/usr/bin/python3 -c "import pyatspi; print('AT-SPI OK')"` para conferir a dependência. Os títulos podem conter dados privados; evite encaminhá-los a provedores remotos se não deseja compartilhar essas informações.

### Importante: lista de janelas AT-SPI é parcial

Após teste real do GNOME Wayland, identificamos que o AT-SPI retornava GNOME Shell, Ptyxis e Nautilus, mas omitia aplicativos que poderiam estar abertos. Isso ocorre porque AT-SPI é uma árvore de **acessibilidade**, não uma API de inventário completo de janelas do compositor. A JARVIS não deve dizer `estas são todas as janelas abertas` com base nela.

A consulta agora retorna `complete: false` e `source: atspi_accessibility_partial`, além de diagnósticos de aplicativos acessíveis, nós inspecionados e falhas de consulta. Para obter a saída bruta, sem interpretação do modelo:

```bash
jarvis-fcc --windows-diagnostic
```

Essa saída permite comparar as aplicações presentes na árvore AT-SPI com janelas visíveis. `not_observed` significa apenas que a janela não apareceu nos objetos inspecionados, **não** que o aplicativo esteja fechado. Para inventário mais completo será necessária uma integração autorizada e específica com o compositor/ambiente GNOME, mantendo o AT-SPI como fonte complementar.

### Reconhecimento de janelas via GNOME Shell (Mutter), com fallback AT-SPI

Os testes locais mostraram que AT-SPI publicou apenas GNOME Shell, Nautilus e Ptyxis. A inspeção completou sem erros (`inspection_failures: 0`, `truncated: false`), portanto o problema não era o limite de busca: Firefox/VS Code podem não expor suas janelas na árvore de acessibilidade.

A JARVIS agora detecta automaticamente a interface D-Bus **read-only** da extensão opcional [Window Calls Extended](https://extensions.gnome.org/extension/4974/window-calls-extended/), mantida para GNOME Shell 45–50. Quando disponível, consulta via `gdbus` o método `org.gnome.Shell.Extensions.WindowsExt.List` para obter título, classe, foco e PID de janelas gerenciadas pelo compositor. Se a extensão não estiver ativa, mantém o inventário parcial AT-SPI.

**Instalação/ativação é uma decisão do usuário.** A JARVIS nunca instala extensão, ativa modo inseguro, chama `Shell.Eval`, nem contorna Wayland. Consulte a página acima, confirme compatibilidade com seu GNOME (`gnome-shell --version`) e habilite a extensão no aplicativo Extensões. Depois faça:

```bash
jarvis-fcc --windows-diagnostic
```

Com a extensão ativa, `source` será `gnome_shell_extension`; se não, permanece `atspi_accessibility_partial` e mostra `fallback_reason`. A própria enumeração de janelas do compositor é marcada como `complete: false`, pois não inclui todas as superfícies possíveis. Títulos de janelas e informações de PID podem ser sensíveis e serão fornecidos ao modelo quando a ferramenta for chamada.

A interface expõe apenas **leitura de janelas**. Não envia comandos de gerenciamento, não solicita permissões novas para clique e não garante que o título mostrado corresponda ao arquivo ativo.

### Execução + observação do GNOME Shell

Com a extensão Window Calls Extended habilitada e o `jarvis-fcc --windows-diagnostic` retornando `source: gnome_shell_extension`, a JARVIS agora tira uma amostra do inventário **antes e depois** de abrir aplicativos com `launch_installed_app`, `open_project` e `open_file`. O resultado contém `window_observation` com um destes estados:

- `appeared_after_request`: surgiu uma janela/título correspondente no inventário após a solicitação (pode ser atualização de título de uma janela preexistente, não prova causalidade).
- `already_observed`: a janela correspondente já constava da amostra anterior.
- `window_changed_after_request`: janela de mesma aplicação/PID tinha outro título antes da solicitação; mudança observada, não nova janela comprovada.
- `observed_unknown_origin`: janela observada, mas o estado anterior estava indisponível.
- `not_observed`: não foi localizada janela correspondente; o lançamento pode ter funcionado.
- `unavailable`: consulta ao compositor indisponível.

São informações complementares. Uma janela observada **não comprova** que o arquivo solicitado está aberto, nem transforma `launched_unverified` em sucesso confirmado. Os resultados são registrados em `managed_processes` durante a sessão (para aberturas com `open_project` ou `open_file`) e anexados como evidência ao plano, sem declarar `completed_verified` para passos de interface gráfica.

Experimente:

```text
Jarvis, abra o Firefox.
Jarvis, crie um projeto Python TesteJanela e abra no VS Code.
Jarvis, mostre os programas que você iniciou nesta sessão.
```

A consulta só ocorre **após autorização de abertura**, não executa comandos de clique ou foco e pode adicionar alguns segundos aos pedidos de lançamento. Perguntas simples não pagam esse custo de observação. O sistema não força fechamento de aplicativos e não acessa a interface insegura `Shell.Eval`.

### Colocar uma janela em primeiro plano (GNOME Wayland; supervisão obrigatória)

Além do **Window Calls Extended** (inventário de janelas), a JARVIS pode usar a extensão separada **[Activate Window By Title](https://extensions.gnome.org/extension/5021/activate-window-by-title/)** para solicitar foco, compatível com GNOME 45–50 na versão atualmente anunciada. Instale e ative a extensão **manualmente**, depois de conferir `gnome-shell --version`. Ela registra `de.lucaswerkmeister.ActivateWindowByTitle.activateByTitle` na sessão D-Bus; não há necessidade de `Shell.Eval`, X11 ou sudo.

A ferramenta `focus_window` exige nome do aplicativo e aceita parte do título para **localizar** uma janela, mas a chamada final usa **sempre o título exato** da correspondência. Antes de executar, ela confere que há uma única janela correspondente, recusa títulos repetidos entre aplicativos, apresenta app+título para você autorizar com `SIM` e revalida o inventário. Depois da resposta da extensão, consulta o GNOME Shell novamente e só retorna `focused_verified` quando a mesma janela de app/título/PID aparece como focada. Não muda foco se a janela já estiver focada.

Se faltar uma das extensões, a ferramenta retornará `unavailable`. Se houver mais de uma janela, retornará `ambiguous` sem escolher arbitrariamente; especifique mais detalhes do título. Se a extensão aceitar a chamada, mas não puder comprovar o foco, o estado será `focus_unverified`, sem promessa de sucesso.

Para testar, primeiro abra duas aplicações comuns (por exemplo, Firefox e VS Code) e digite:

```text
Jarvis, identifique a janela do Firefox e coloque-a em primeiro plano.
```

A JARVIS deverá solicitar sua autorização explícita. Para um teste sem alterar foco, use `jarvis-fcc --windows-diagnostic`. A extensão de ativação não é instalada pelo `pip install` e não foi testada fisicamente no notebook do usuário nesta versão; a confirmação em GNOME real é a próxima validação.


### Fluxo integrado de abertura + foco e desempenho (22/10/2026)

A JARVIS agora oferece três ferramentas supervisionadas para solicitações **explícitas** de abertura e foco:

- `open_project_and_focus`: abre projeto no VS Code/VSCodium e tenta focar uma janela única cujo título contém o nome da pasta.
- `open_file_and_focus`: abre arquivo no editor e tenta focar uma janela única cujo título contém o nome do arquivo.
- `launch_installed_app_and_focus`: abre aplicativo conhecido do catálogo XDG e tenta focar uma janela única da classe correspondente.

Em todos os casos o **lançamento exige aprovação**, e a **mudança de foco exige aprovação separada** se a janela ainda não estava focada. As respostas têm campos independentes `launch` e `focus`: um `launch.status=launched_unverified` **não prova** que o foco teve sucesso; somente `focus.status=focused_verified` confirma observação do foco no GNOME.

Para evitar lentidão, as amostras antes/depois da abertura agora usam diretamente o serviço D-Bus do GNOME Shell, com limite menor de espera. O inventário completo da CLI (`--windows-diagnostic`) mantém fallback AT-SPI para diagnósticos. Quando o serviço do GNOME não responde, a observação da abertura é marcada `unavailable`, sem consultar demoradamente o AT-SPI nem afirmar que o programa falhou.

Teste, após `git pull --ff-only origin main` e ativar `.venv`:

```text
Jarvis, abra o Firefox e coloque sua janela em primeiro plano.
Jarvis, abra meu projeto TesteJanela no VS Code e coloque sua janela em primeiro plano.
```

Se os títulos diferirem, ou houver janelas duplicadas, o foco será recusado ou não observado — não há busca agressiva nem clique cego. É necessário manter **Window Calls Extended** e **Activate Window By Title** habilitadas. Os tempos totais também dependem da inferência do FCC: depois de uma interação execute `/metricas` para separar `model_s` (modelo) do tempo total. A validação física desses novos fluxos no notebook ainda está pendente.

### FCC: NIM alternou para diffusiongemma e rejeitou assistant vazio (22/10/2026)

Se aparecer `Empty content is not allowed for assistant messages` depois de uma chamada de ferramenta, o agente agora filtra mensagens do assistente sem conteúdo útil antes de reenviar o histórico ao FCC, mantendo os pares `function_call` e `function_call_output`. Essa correção evita um formato de histórico que certos provedores rejeitam.

Em pedidos **com ferramentas**, a JARVIS não faz mais fallback implícito para modelos arbitrários do mesmo provedor anunciados no catálogo Responses — a lista não garante compatibilidade com function calling. Ela só tentará candidatos adicionais configurados explicitamente via `FCC_FALLBACK_MODELS`. Pedidos sem ferramentas mantêm a política de fallback anterior. Falhas reais do modelo continuam sendo exibidas.

Se o padrão do FCC for `nvidia_nim/nvidia/nemotron-3-super-120b-a12b` e a JARVIS estiver lenta, primeiro compare modelos sem misturar provedores:

```bash
cd ~/free-jarvis
git pull --ff-only origin main
source .venv/bin/activate
jarvis-fcc --models
# Somente se o ID estiver anunciado e for autorizado na sua instalação:
export FCC_MODEL='openai/gpt-5.6-luna'
unset FCC_FALLBACK_MODELS FCC_ALLOW_CROSS_PROVIDER
jarvis-fcc
```

Dentro do chat use `/metricas` **depois** de fazer uma pergunta. Compare `model_s` e `total_s`. Se o modelo explícito estiver indisponível, use `jarvis-fcc --models` para escolher outro ID real; não tente contornar erros de 400 repetidamente. A correção foi coberta por testes simulados; comportamento no FCC/NIM do notebook ainda requer validação.

### Resposta atrasada após focar Firefox — correção (22/10/2026)

Teste real confirmado no notebook: a chamada `focus_window` solicitou `SIM`, e o Firefox foi colocado em primeiro plano. Entretanto, após executar a ação, a JARVIS ficou aguardando a **segunda requisição de inferência ao FCC** (para narrar o resultado); o usuário interrompeu o processo com Ctrl+C, gerando `KeyboardInterrupt` dentro de `urllib.request.urlopen`. Portanto, o gargalo registrado não era a execução D-Bus do foco, mas a espera de resposta HTTP após a ferramenta ter concluído. Isso não indica que o FCC esteja definitivamente travado.

Agora, quando a IA solicita **somente** `focus_window` em uma operação explícita de foco, a JARVIS devolve imediatamente um texto determinístico a partir do resultado real da ferramenta, sem executar uma segunda rodada do modelo. Sucesso só é declarado quando o GNOME devolve `focused_verified` ou `already_focused`. Recusas, ambiguidades e falta de confirmação são descritas sem alegar sucesso. Com várias ferramentas na mesma rodada, mantém a interação normal com o modelo. `/metricas` indica `direct_tool_reply: true` e normalmente `model_rounds: 1`.

Se você interromper uma geração com Ctrl+C, a CLI permanece no chat, em vez de encerrar com traceback. A execução pode já ter aplicado ações locais: **verifique o estado real antes de repetir a solicitação**. `/metricas` na mesma sessão exibe o que estava registrado ao interromper; ao iniciar um processo novo, não existem métricas da sessão antiga.

```bash
cd ~/free-jarvis
git pull --ff-only origin main
source .venv/bin/activate
jarvis-fcc
```

Diga: `Jarvis, coloque o Firefox em primeiro plano`. Se ele já estiver focado, espere mensagem `already_focused`. Depois solicite `/metricas`. A correção é um caminho curto somente para foco isolado, não uma promessa de eliminar toda a latência de modelos FCC.

## JARVIS v0.2.0 — autorizações automáticas por sessão

Você pode ativar o modo de execução sem digitar `SIM` repetidamente:

```bash
cd ~/free-jarvis
git pull --ff-only origin main
source .venv/bin/activate
jarvis-fcc --auto-approve
```

Dentro da JARVIS também estão disponíveis:

- `/permissoes auto`: ativa autoaprovação **na sessão atual**.
- `/permissoes manual`: volta a solicitar `SIM` para ações.
- `/permissoes status`: mostra o modo e o contador de operações autoautorizadas.

O modo padrão continua manual, salvo quando `--auto-approve` for usado. Cada aprovação automática aparece no terminal como `⚡ AUTOAUTORIZADO (sessão): ...`. **Atenção:** no modo automático, a JARVIS pode criar, alterar ou mover arquivos do workspace, abrir apps e URLs e interagir com ferramentas existentes sem perguntar. Uma instrução equivocada da IA pode causar efeitos reais. Monitore as ações e prefira `/permissoes manual` quando estiver trabalhando com dados importantes.

**O que esse modo NÃO faz:** não confere permissões de administrador/root, não contorna diálogos de permissão do GNOME/Wayland, não adiciona execução genérica de shell, não modifica permissões Unix, não acessa pastas fora de `JARVIS_WORKSPACE` e `JARVIS_ALLOWED_DIRS`, nem amplia o catálogo de ferramentas permitido. O controle de escopo e validação dos caminhos permanece no `Toolkit`. A autorização automática vale somente para as solicitações de consentimento internas da JARVIS, não para permissões do sistema.

Para o modo automático permanecer habilitado em novas sessões, use `jarvis-fcc --auto-approve` na forma habitual de iniciar. A autoaprovação é interrompida ao sair da sessão e só será reativada com uma escolha explícita do usuário.

## JARVIS v0.3.0 — minimizar, restaurar e maximizar janelas no GNOME Wayland

Adicionada a ferramenta `manage_window`, com operações `minimize`, `restore`, `maximize` e `unmaximize`, preservando `focus_window` para colocar janelas em primeiro plano.

**Requisito opcional adicional:** [Window Control](https://extensions.gnome.org/extension/10886/window-control/) — extensão GNOME separada de Window Calls Extended e Activate Window By Title. É instalada e habilitada pelo usuário. Verifique a compatibilidade com `gnome-shell --version` e as extensões ativas via `gnome-extensions list --enabled`. O UUID usado pelo projeto é `window-control@carlo9890.github.io`. Após instalar uma extensão no GNOME Wayland, talvez seja necessário sair e entrar novamente na sessão para carregá-la.

Essa extensão disponibiliza `org.gnome.Shell.Extensions.WindowControl.ListDetailed` e comandos `Minimize`, `Unminimize`, `Maximize`, `Unmaximize` via D-Bus. Nossa JARVIS **não** instala extensões automaticamente, não chama `Shell.Eval`, não usa `xdotool`/X11 para controlar janelas Wayland e não implementa fechamento de janelas nesta versão.

A ferramenta consulta janelas por classe/título, exige uma única correspondência, obtém ID do GNOME (não o recebe da IA), pede confirmação ou usa `--auto-approve` quando habilitado, relê o inventário depois da autorização e chama o D-Bus do Window Control. Só retorna `state_verified` se o estado final for confirmado; quando impossível validar, retorna `state_unverified` ou outro estado de falha. Se a extensão não estiver carregada, retorna `unavailable` e não tenta contornar a ausência.

Exemplos:

```text
Jarvis, minimize a janela do Firefox.
Jarvis, maximize a janela do Firefox.
Jarvis, restaure a janela do Firefox.
Jarvis, desmaximize a janela do Firefox.
```

Para não precisar digitar `SIM`:

```bash
cd ~/free-jarvis
git pull --ff-only origin main
source .venv/bin/activate
jarvis-fcc --auto-approve
```

O roteador anuncia apenas `manage_window` para pedidos de estado de janela inequívocos, evitando enviar o catálogo completo à IA. A resposta após uma ação isolada vem diretamente da ferramenta, sem outra chamada ao FCC, e `/metricas` registra `tools_advertised`, `model_rounds` e `direct_tool_reply`.

**Aviso:** a interface D-Bus do Window Control não possui controle de acesso próprio dentro da sessão GNOME. Como qualquer programa da sessão pode potencialmente usá-la, avalie esse aspecto antes de instalar. O usuário controla a instalação e a ativação. O funcionamento real precisa ser testado no notebook; o CI valida apenas comportamentos simulados e não controla um GNOME físico.

Referências técnicas da extensão: https://github.com/carlo9890/gnome-window-control e https://github.com/carlo9890/gnome-window-control/blob/main/window-control@carlo9890.github.io/dbus-interface.js
