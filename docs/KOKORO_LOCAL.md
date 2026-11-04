# Kokoro local com pf_dora — integração de 04/11/2026

O seletor em Configurações → Voz → Saída oferece Piper e Kokoro. Piper permanece
padrão, incluindo preferências antigas. O botão **Instalar e selecionar Kokoro +
Dora** prepara dependências e pesos explicitamente, verifica-os e salva a seleção
somente ao concluir. Falha não altera a voz anterior. Instalar não comprova áudio
audível. A resposta visual permanece disponível se a síntese ou o player falhar.

## Preparação por CLI

```bash
jarvis-fcc kokoro status
jarvis-fcc kokoro install-runtime
jarvis-fcc kokoro install-voice
jarvis-fcc kokoro test --output /tmp/dora-teste.wav
jarvis-fcc kokoro select
```

`install-runtime` exige `uv` e Python compatível já instalado; procura Python 3.12
sem baixar um interpretador. `--python CAMINHO` seleciona outro Python >=3.10 e
<3.13. `--offline` usa somente cache. [Kokoro 0.9.4](https://pypi.org/project/kokoro/0.9.4/)
exclui Python 3.13/3.14; por isso não é instalado na venv da GUI nem na do OpenJarvis.
O ambiente fixa Kokoro/Misaki 0.9.4, Transformers 4.51.3 e Torch 2.8.0+cpu,
obtido pelo índice oficial CPU do PyTorch. Verifica versões e fonemizador pt-BR
sem carregar os pesos. Não executa instalação administrativa de pacotes do sistema.

O runtime gerenciado fica em `~/.local/share/jarvis-fcc/kokoro-runtime/versions/`.
Sua localização é publicada atomicamente após verificação, sem mover a venv.
Instalações repetidas reutilizam um ambiente válido; falhas deixam o ambiente
anterior e removem somente a tentativa nova. Usa o mesmo executor de preparação,
cancelamento e lock já empregado no provisionamento Local. Parar é propagado ao
processo e seus filhos. Não há downloads no startup nem durante fala cotidiana.

`install-voice` baixa ~328 MB de pesos/voz e metadados, fora do Git. Dependências
CPU são um download separado. `--directory PASTA` permite outra localização.
Origem, revisões, licença Apache-2.0 e hashes ficam em `SOURCE.json`, junto do
model card. Pesos e voz têm SHA256 esperado publicado nas páginas oficiais:

| Artefato | Revisão | SHA256 |
| --- | --- | --- |
| [kokoro-v1_0.pth](https://huggingface.co/hexgrad/Kokoro-82M/blob/41e5892b9d8b43e56fc560f892312a328a410973/kokoro-v1_0.pth) | `41e5892b9d8b43e56fc560f892312a328a410973` | `496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4` |
| [pf_dora.pt](https://huggingface.co/hexgrad/Kokoro-82M/blob/a3ebfcc2bb43e3d8df8199d4081f4fc6d310cc6d/voices/pf_dora.pt) | `a3ebfcc2bb43e3d8df8199d4081f4fc6d310cc6d` | `07e4ff987c5d5a8c3995efd15cc4f0db7c4c15e881b198d8ab7f67ecf51f5eb7` |

Configuração e model card vêm da revisão imutável dos pesos; seus hashes são
registrados no primeiro download explícito e revalidados depois. O instalador
também confere configuração e declaração de licença. Nenhum pickle arbitrário é
aceito como voz: só os arquivos oficiais fixados. O carregador upstream usa
`weights_only=True`. O cache do modelo é invalidado se os arquivos selecionados
mudarem; a verificação completa ocorre ao carregar o worker, evitando ler centenas
de MB a cada frase.

`test` sintetiza uma frase controlada em WAV PCM16 mono a 24 kHz, sem microfone ou
player. Não sobrescreve arquivo existente. `select` verifica pesos/runtime e salva
preferências sem reproduzir. Para áudio físico, use **Testar voz salva** na GUI,
na saída Pulse/PipeWire selecionada. Não se registra “audível” automaticamente.

`status` e `--doctor` fazem apenas diagnóstico básico; não carregam Kokoro ou
Torch nem verificam hashes grandes. Diferenciam presença/configuração de teste
funcional pendente. `JARVIS_TTS_BACKEND`, `JARVIS_KOKORO_DIRECTORY` e
`JARVIS_KOKORO_PYTHON` prevalecem sobre preferências. Campos de diretório/Python
vazios usam recursos gerenciados. `JARVIS_KOKORO_RUNTIME_DIR` altera a raiz do runtime.

## Fluxo normal e cancelamento

CLI e GUI usam a mesma seleção persistente e `VoiceIO`. A fila de duas WAVs,
segmentação por frases, player, saída escolhida e proteção de captura durante
TTS são os existentes. Não foi criado outro executor de conversa ou ferramentas.
Uma falha de voz não reexecuta a ação solicitada.

Kokoro é carregado uma vez em processo separado, com CPU e duas threads. A troca
de backend encerra o sintetizador anterior antes de carregar o próximo, limitando
a uma voz residente. O processo lê somente arquivos locais; downloads HF ficam
desabilitados e tentativas de conexão Python são recusadas. Isso não substitui
um ensaio com bloqueio externo de rede do sistema.

A integração passa `KModel` com caminhos locais a `KPipeline(lang_code='p')` e usa
o arquivo `pf_dora.pt`. A [lista oficial de vozes](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
identifica `p` e `pf_dora` para português brasileiro. O caminho padrão da versão
consultada pode truncar sequências de fonemas acima do limite. Aqui, o G2P divide
recursivamente o texto antes de `generate_from_tokens`; não usa um corte por slice
nem descarta o restante. Frase final sem pontuação segue pela mesma fila.

Parar cancela síntese, invalida o worker bloqueado e recolhe o subprocesso; a fila
e o player existentes descartam os WAVs atrasados. A próxima tentativa cria um
worker novo. A saída só é aceita após conferência do WAV. Excesso de duração ou
áudio inválido gera erro e preserva o texto, sem afirmar que a fala foi concluída.

## Evidência e aceite pendente

Automação cobre preferências antigas, seleção pela GUI, falha/retry de instalação,
hash/licença, publicação, cache residente, cancelamento, timeout, recuperação,
isolamento do Piper e fila ordenada. Geração de PCM e fonemização nesses testes
usam adaptadores controlados; não provam qualidade ou fala real de pf_dora.

Neste ambiente, a tentativa real de instalar o runtime falhou porque Torch CPU
não estava em cache; a tentativa dos pesos falhou por DNS. Nenhum peso foi
instalado, nenhum ambiente parcial foi selecionado e o padrão Piper foi mantido.
O teste real opcional é ignorado sem acionamento explícito:

```bash
JARVIS_TEST_KOKORO_WAV=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_kokoro.py -q
```

Após provisionar, ainda é necessário medir carga fria/aquecida, primeira frase,
memória com STT e conversa ativos, recuperação e cancelamento real, além de ouvir
a saída Bluetooth sem internet. Não houve captura ambiental ou reprodução física
neste incremento. Não se declara a etapa Voz aceita nem barge-in disponível.
