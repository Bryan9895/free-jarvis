# Engenharia: execução verificada e retomada

Checkpoint de 05/11/2026, sobre `df02ce76beabbcc3c6c9b5cf9ce7a3e06c7d725a`.

O fluxo agora consegue verificar pós-condições explícitas de um processo antes
de avançar no planejador. A fixture exercita clone local, venv real, instalação
de uma wheel própria pelo cache, configuração, testes, HTTP e retomada. A
interpretação pelo FCC real continua pendente nesta sessão, que bloqueia DNS e
conexões de aplicação; nenhum resultado controlado é apresentado como aceite FCC.

## Pós-condições de processo

`execute_process` preserva suas autorizações de terminal/dados, argv sem shell,
prazo, limite de saída e cancelamento do grupo. Sem `postconditions`, saída zero
continua significando processo encerrado, sem comprovar o objetivo.

O campo opcional aceita:

- `project` e `revision`: projeto autorizado com SHA Git esperado.
- `project` e `distributions`: nomes de distribuições presentes nos metadados
  da venv. Isso não prova importação, integridade de todo o pacote ou seus testes.
- `files`: arquivos autorizados até 100 KB, cada um com caminho e SHA256 esperado.
- `stdout_sha256`: SHA256 exato da saída padrão UTF-8 capturada, incluindo quebras
  de linha. Saída truncada ou processo com código diferente de zero não passa.

Exemplo de estrutura, usando valores obtidos por leitura/verificação prévia:

```json
{
  "argv": ["/caminho/projeto/.venv/bin/python", "test_suite.py"],
  "cwd": "/caminho/projeto",
  "postconditions": {
    "project": "/caminho/projeto",
    "revision": "SHA_GIT_OBSERVADO",
    "distributions": ["jarvis-fixture-dep"],
    "files": [{"path": "/caminho/projeto/config.json", "sha256": "SHA256_OBSERVADO"}],
    "stdout_sha256": "SHA256_DA_SAIDA_ESPERADA"
  }
}
```

Os marcadores do exemplo precisam ser substituídos por hashes válidos, nunca
inventados pelo modelo. O validador rejeita condições vazias, esquema incorreto
e caminhos não autorizados antes de iniciar o processo. Após saída zero, observa
as condições de novo; divergência suspende o plano. A verificação atesta somente
essas condições, sem afirmar que outros efeitos do programa foram corretos.

O agente preserva evidências sanitizadas no checkpoint SQLite, sem gravar stdout,
código de arquivos ou argv como novos campos de auditoria. Na retomada, o
planejador revalida revisão, ambiente/distribuições declarados e hashes de
arquivos. A saída de testes é um fato histórico: não se roda o processo novamente
para conferi-la. Use também condições atuais de ambiente/arquivos para vincular
esse resultado ao projeto; uma prova contendo apenas stdout não permite retomada
automática. Escritas verificadas também guardam o hash para detectar alterações
posteriores da configuração.

## Jornada dirigida

`tools/validate_engineering.py` usa `JarvisService`, `Agent`, `TaskPlanner`,
`PlanStore`, `Toolkit` e as ferramentas existentes. Não introduz outro executor
ou planejador. A origem controlada contém:

- Projeto Git pequeno, com README e configuração a preservar.
- Wheel determinística `jarvis-fixture-dep==1.0.0`, criada localmente; o
  `requirements.txt` fixa seu SHA256.
- Preparação de venv e pip com `--isolated --no-index --require-hashes --no-deps`.
  O preparo recusa uma venv já existente, tornando repetição acidental visível.
- Dois testes que importam a dependência real e verificam a configuração.
- Servidor HTTP de loopback que importa a mesma dependência e fornece `/health`.

As cinco etapas são clone com SHA, instalação, configuração, testes e serviço.
No teste de retomada, uma falha dirigida interrompe a quarta etapa. O serviço
Jarvis é fechado e reconstruído com o mesmo SQLite; após decisão explícita de
retry, somente testes e início do serviço voltam à fila. O health é verificado
com identidade/porta do processo. Repetir start reutiliza o mesmo PID/starttime.
Alterar config.json antes da retomada bloqueia a execução antes do próximo comando.

No terminal normal, a execução controlada cria um diretório novo e produz um
relatório sanitizado:

```bash
PYTHONPATH=src python tools/validate_engineering.py \
  --directory /tmp/jarvis-engenharia-nova --output /tmp/jarvis-engenharia.json
```

O harness encerra o serviço de teste ao final, registra o resultado da limpeza e
retorna código 1 se o plano não ficou completamente verificado ou a limpeza falhou.
Não executa áudio nem altera concessões persistentes. No modo controlado, as
aprovações são apenas de memória para chamadas fixas da fixture.

Para o ensaio futuro com FCC real, use outro diretório novo e `--fcc`. As
autorizações são interativas, preservando o fluxo normal de permissões; o ensaio
pode consumir cota e não comprova, por si, que o FCC encaminhou para um modelo
local. Um plano interrompido pode ser inspecionado no SQLite e retomado com
`--resume`. Etapa incerta exige decisão explícita `--resolve retry` ou
`--resolve skip`; não há repetição automática de instalação ou clone.

## Evidências e pendências

Os testes automatizados executam operações reais de Git, venv/pip com wheel
local e HTTP. A interpretação do modelo é controlada. Cobrem falha/retomada após
reabrir SQLite, ausência de clone/reinstalação duplicados, configuração preservada,
mesma identidade no start repetido e suspensão após edição da configuração.
Também cobrem saída zero sem condição, hash divergente, saída não zero e rejeição
de condição inválida antes dos efeitos.

O aceite real FCC, o perfil Local sem internet, os modelos/Kokoro e os ensaios de
voz/Bluetooth permanecem separados e pendentes. Não foram alterados os defaults
de voz/modelo nem as alterações locais anteriores de equipe.
