# Perfil Local — checkpoint de 04/11/2026

Base: `d5eedae1312894037d9de330985296dd9720dcb3`. A especificação mais recente
em `/home/bryan/Documentos/99_Arquivo/AGENTS.md` substitui a decisão histórica de
usar OpenJarvis apenas como referência. Este checkpoint entrega o adaptador;
o aceite de Casa/Motor/Cérebro exige inferência e ensaios offline reais.

CLI e GUI mantêm `jarvis-fcc` e selecionam explicitamente FCC ou OpenJarvis.
`OllamaEngine.stream_full` recebe mensagens e ferramentas. O worker converte
texto, chamadas e resultados para o contrato Responses existente. Somente
Agent/Toolkit do Free-Jarvis executam efeitos, mantendo validação e autorização.
OpenJarvis é dependência Apache-2.0, sem código upstream copiado no adaptador.

## Provisionamento explícito

O Jarvis neste notebook usa Python 3.14; OpenJarvis fixado exige >=3.10 e <3.14.
Com `uv` e um Python compatível já instalados, o Jarvis cria, verifica e seleciona
um ambiente gerenciado, sem mudar o perfil FCC existente:

```bash
jarvis-fcc local install-engine
# Python explícito e somente cache, sem downloads:
jarvis-fcc local install-engine --python /caminho/python3.13 --offline
jarvis-fcc local status
jarvis-fcc local status --json
```

Sem `--python`, procura Python 3.13 já disponível pelo `uv`, em modo offline;
não baixa um interpretador. A instalação de dependências usa rede apenas no
comando explícito e pode ser limitada ao cache com `--offline`. A versão fixada
é verificada em subprocesso antes da publicação. Uma segunda execução reutiliza
o ambiente válido. Falhas, timeout, cancelamento e instalações simultâneas não
sobrescrevem um ambiente funcional. O caminho de cada venv é definitivo desde
a criação, preservando shebangs; somente `runtime.json` é substituído atomicamente.
Ambientes anteriores são preservados, sem remoção automática de dependências.

O ponteiro fica em `~/.local/share/jarvis-fcc/local-runtime/runtime.json`;
`JARVIS_LOCAL_RUNTIME_DIR` permite outra raiz. CLI e GUI o consultam sem subprocesso,
inferência ou rede no startup. Um `JARVIS_OPENJARVIS_PYTHON` não vazio tem precedência.
O provisionamento automático está limitado ao Linux; Windows requer validação própria.

A preparação manual anterior continua disponível:

```bash
python3.13 -m venv ~/.local/share/jarvis-fcc/openjarvis-venv
~/.local/share/jarvis-fcc/openjarvis-venv/bin/python -m pip install -r requirements/openjarvis.txt
export JARVIS_OPENJARVIS_PYTHON="$HOME/.local/share/jarvis-fcc/openjarvis-venv/bin/python"
```

O worker exige origem oficial e commit
`324c9c3ac61bff07a0d99b715a7511dcd78600c4` em `direct_url.json`. Outra revisão,
inclusive instalação editable sem essa proveniência, é recusada. Instalar a
dependência é provisionamento do produto; não se executa setup só para análise.
O uso diário não instala dependências nem baixa pesos.

Instale Ollama pelo [guia oficial](https://docs.ollama.com/linux), com servidor
em loopback. Baixe pesos somente durante o provisionamento:

```bash
jarvis-fcc local pull-model gemma4:e2b
# Alternativa pequena citada na configuração histórica do projeto:
jarvis-fcc local pull-model qwen3.5:2b
# Teste ativo curto de texto, sem ferramentas, microfone ou reprodução:
jarvis-fcc local check
```

`pull-model` usa o Ollama já instalado e o endpoint de loopback configurado;
não instala binários do sistema. `status` não consulta o daemon nem abre dispositivos.
`check` conecta e infere explicitamente, mas não comprova isolamento externo de rede
nem áudio audível. Servidor ausente é distinguido de um modelo não instalado.

Confira os modelos instalados antes de comparar. O catálogo
[Gemma 4](https://ollama.com/library/gemma4) inclui variantes locais e remotas;
não existe vencedor aprovado neste checkpoint.

## Seleção e persistência

```bash
jarvis-fcc --profile local --local-model gemma4:e2b --save-profile
jarvis-fcc --text-only
jarvis-fcc --gui
# Sessão de engenharia preservando FCC_URL/FCC_MODEL antigos:
jarvis-fcc --profile fcc --text-only
```

`--save-profile` grava preferências atomicamente e sai sem inferência ou áudio.
Sem essa opção, `--profile` vale para a execução. `JARVIS_PROFILE` e
`JARVIS_LOCAL_MODEL` explícitos prevalecem sobre preferências. O Python gerenciado
é encontrado automaticamente; o caminho manual pode ficar no ambiente. Reinicie após mudar o perfil. Instalações antigas
continuam em FCC. A GUI informa o perfil em Configurações → Modelos. Selecionar
modelo nessa aba ou com `/modelo ID` persiste `local_model`, separado do modelo
FCC. Whisper continua separado do modelo de conversa.

O endpoint padrão é `http://127.0.0.1:11434`, configurável por
`JARVIS_OLLAMA_HOST`: somente HTTP com IP literal de loopback e porta, sem
credenciais/path/query/fragmento. Proxy de ambiente e redirects são desabilitados.
Tags `:cloud`, `remote_host`/`remote_model` em `/api/show` e referência `:cloud` no
Modelfile bloqueiam inferência. Os campos remotos constam dos
[tipos oficiais do Ollama](https://github.com/ollama/ollama/blob/main/api/types.go).
Um daemon em loopback continua sendo componente confiável: comprovar ausência
de roteamento remoto exige bloquear também sua saída para internet no ensaio.

Não há descoberta/fallback de provedores ou fallback automático de modelos no
perfil Local. Para chamadas estruturadas, o modelo deve anunciar `tools`.
O retry upstream que remove ferramentas após HTTP 400 foi desabilitado: falha
de contrato continua visível. Visão e diagnósticos ativos exclusivos FCC exigem
seleção explícita desse perfil.

## Limites e validação

O catálogo Local contém operações internas de arquivos e tarefas. Navegador,
processos arbitrários, administração e plugins aguardam confinamento de rede.
O Toolkit também bloqueia essas operações no limite de execução, mesmo após
reativar capacidades. FCC preserva suas ferramentas. Captura, ativação e TTS
existentes não foram substituídos.

Um worker é criado e recolhido por requisição; o modelo permanece sob o ciclo
de vida do Ollama. O custo de startup Python por rodada ainda precisa ser medido.
O deadline inclui preflight e espera; cancelamento é consultado a cada 50 ms e
recolhe o worker bloqueado. Texto parcial permanece; resposta incompleta não
entrega chamadas executáveis. IPC selectors/pipes foi validado no Linux;
Windows permanece pendente.

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
git diff --check
# Fonte OpenJarvis em checkout exato da revisão fixada, sem Ollama/modelo:
~/.local/share/jarvis-fcc/openjarvis-venv/bin/python -I tests/check_openjarvis_contract.py --source /caminho/OpenJarvis-fixado
```

O último teste usa o motor upstream real com `httpx.MockTransport`: valida SHA,
streaming, ID/argumentos, replay de resultado e ausência de retry no 400. Não
comprova inferência. A suíte cobre compatibilidade, persistência, bloqueio remoto,
ação de arquivo via controlador/serviço/Toolkit, cancelamento, deadline, texto
final sem ponto, EOF parcial e recolhimento do subprocesso.

Após provisionamento, com FCC parado e internet bloqueada também para o Ollama:

```bash
JARVIS_LOCAL_MODEL=gemma4:e2b PYTHONPATH=src .venv/bin/python -m jarvis.benchmark --local --samples 30 --output /tmp/jarvis-gemma4.json
JARVIS_LOCAL_MODEL=qwen3.5:2b PYTHONPATH=src .venv/bin/python -m jarvis.benchmark --local --samples 30 --output /tmp/jarvis-qwen.json
```

O benchmark reaproveita pedidos e verificação de arquivos/tarefas em workspace
temporário, sem persistir prompts/respostas. Reporta primeiro texto, tempo total,
p50/p95 por cenário e erros. Para N=30 por classe, use `--scenario short_question`,
`long_answer`, `simple_action` e `compound_action`. O caso simples pode usar
handler determinístico; o composto deve demonstrar chamada produzida pelo modelo.
As métricas por turno de CPU/RSS medem só o processo principal; o bloco de RAM
descrito abaixo amplia a cobertura. Ainda é preciso medir carga fria/aquecida,
qualidade pt-BR, chamadas inválidas e
recuperação, com STT/TTS ativos e reprodução Bluetooth. Não publique latência,
vencedor ou aceite offline sem esses ensaios. O padrão só muda após aceite real.

### RAM dos workers e do daemon

`rss_kib` e `cpu_s` por turno continuam compatíveis e medem o processo principal.
O bloco `memory` do relatório agora amostra `/proc` a cada 50 ms: soma RSS e PSS
dos descendentes, acompanha RAM disponível/uso global do sistema e reporta erros
ou cobertura incompleta. Não lê linhas de comando, prompts ou transcrições.
Para incluir um daemon Ollama iniciado fora da árvore do benchmark:

```bash
JARVIS_LOCAL_MODEL=gemma4:e2b PYTHONPATH=src .venv/bin/python -m jarvis.benchmark --local --samples 30 --monitor-pid PID_DO_OLLAMA --output /tmp/jarvis-gemma4.json
```

`--monitor-pid` é repetível e somente lê métricas; não envia sinais ao daemon.
PIDs ausentes ficam explícitos. PSS fica nulo quando não puder ser lido para toda
a árvore selecionada. Somar RSS pode contar páginas compartilhadas mais de uma
vez; prefira PSS. Os picos são amostrados e podem perder alocações mais curtas
que 50 ms. O uso global de RAM inclui os outros aplicativos do notebook.
Não compare modelos simultâneos num notebook de 8 GB: descarregue o anterior
com `ollama stop NOME` antes de iniciar o seguinte, conforme a
[documentação de ciclo de vida](https://docs.ollama.com/faq).

### Evidência de instalação em 04/11/2026

Foi possível instalar o motor fixado no ambiente gerenciado, em Python 3.13.15,
reutilizando cache de pacotes e uma cópia Git local rasa da revisão oficial já
obtida. A substituição de URL Git por mirror foi limitada ao processo de instalação;
nenhuma configuração Git global foi alterada. A instalação VCS registrou origem
oficial e SHA em `direct_url.json`. O wheel veio do commit fixado e sua versão
dinâmica no mirror raso ficou `0.0.1.dev1+unknown.g324c9c3ac`; o aceite usa o SHA,
não infere outra versão upstream a partir desse número. Uma instalação posterior
por `local install-engine --offline` foi concluída, publicada e reaproveitada.

Ollama não foi localizado. Downloads diretos falharam por DNS, sockets inclusive
loopback foram negados e `bwrap --unshare-net` não pôde criar namespace nesta
execução. Não houve tentativa de mudar firewall, conceder permissões amplas ou
anunciar inferência/aceite offline. A suíte usa o comando de testes já autorizado
para seu HTTP controlado; isso não representa a disponibilidade de rede da sessão
normal do agente. A comparação real Gemma/Qwen continua pendente.
