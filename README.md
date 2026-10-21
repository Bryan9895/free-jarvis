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
