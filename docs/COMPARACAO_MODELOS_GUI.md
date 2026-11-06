# Comparação Local e revisão de qualidade pela GUI

Checkpoint de 06/11/2026 sobre `76e52f49e6dcaac5c13d726bf514a5906ee8ac20`.
Esta entrega integra o comparador existente à interface. Não há candidato vencedor
real aprovado neste checkpoint: Ollama continua ausente no ensaio normal e a
consulta oficial do instalador falhou com `URLError`.

## Preparar e executar

Em **Configurações → Configuração inicial**, prepare o motor, instale/inicie
Ollama e baixe explicitamente dois candidatos. Use **Comparar modelos preparados**
ou abra **Configurações → Comparar modelos**. A comparação não instala modelos,
não usa FCC e não altera preferências.

Informe os dois nomes locais já instalados. Para o servidor iniciado pela janela,
deixe PID vazio: o backend obtém seu PID e confere a porta. Para um servidor
externo, informe o PID do processo Ollama que possui a porta configurada. A
identidade Linux é conferida antes e depois das medições; reinício/troca de PID
invalida o ensaio. Medir um processo arbitrário como se fosse RAM do daemon é
recusado antes da inferência.

Clique **Executar comparação e arquivar respostas** e escolha uma pasta privada
fora de Git. O fluxo cria um subdiretório novo, 0700, sem substituir outro ensaio.
Abrir o painel ou um relatório não infere, baixa pesos ou abre dispositivos.

O protocolo preserva seis cenários: pergunta curta, resposta longa, ação simples,
ação composta, negação e ação com números. São três turnos frios e trinta
aquecidos por cenário/modelo: **198 por candidato, 396 ao todo**. Frio significa
pesos descarregados do Ollama; o cache de disco do sistema não é limpo. O último
turno frio aquece o mesmo modelo para os trinta seguintes. O modelo é descarregado
antes de começar o outro candidato e na limpeza; falha de descarga não passa
como ensaio válido.

O benchmark usa o controlador, serviço, Agent e Toolkit existentes. Arquivos e
tarefas dirigidas ficam em workspace/SQLite temporários, com capacidades limitadas
e política Local. Processos arbitrários, plugins, navegação ou arquivos do usuário
não são habilitados por esse ensaio. A ação composta verifica efeitos e observa
chamadas estruturadas no mesmo fluxo normal. Os tempos de primeiro texto/total,
p50/p95, erros e memória vêm do benchmark existente, sem sintetizar áudio.

Ações simples e numéricas podem usar o handler local existente. Mede-se o fluxo
do aplicativo, não só a capacidade isolada do modelo. A ação composta exige pelo
menos duas chamadas de ferramenta observadas no caminho do modelo; o contador
`model_tool_calls_observed` não atribui ao modelo chamadas do handler local.

O ensaio roda na fila local, fora de Tk e sem esperar conexão FCC. Mostra modelo,
cenário, fase e progresso por lote. Não troca `JARVIS_LOCAL_MODEL` globalmente:
cada medição recebe uma configuração explícita. A sessão de conversa atual e seu
perfil continuam selecionados.

## Parar e resultados parciais

**Parar comparação** cancela preflight e inferência, compartilha cancelamento
com cada turno e descarta resultados atrasados. Os deadlines de cada turno ficam
em tokens filhos; o primeiro turno não encurta o orçamento de toda a comparação.
Na GUI, o limite total é de quatro horas. Limites existentes por turno continuam
valendo.

Na limpeza, há tentativa separada de descarga com prazo de cinco segundos;
cancelar o ensaio não cancela essa limpeza. Os workers de inferência são
recolhidos pelos adaptadores. A janela continua responsável somente pelo daemon
que iniciou; um servidor externo não é encerrado.

Medições já recebidas e respostas dirigidas ficam no novo diretório. Cancelamento,
falha ou ensaio incompleto não indicam vencedor. Retomar a revisão de um ensaio
concluído não repete inferências. Recomeçar medições é uma nova execução explícita,
em outro diretório; não há retomada silenciosa de efeitos do benchmark.

## Arquivos e revisão humana

Os arquivos são privados, com publicação atômica dos JSONs e permissão 0600:

| Arquivo | Conteúdo |
| --- | --- |
| `metrics.json` | Tempos, RAM, estados, identidades e digest; sem pedidos/respostas |
| `responses.jsonl` | Pedidos dirigidos e respostas do benchmark, sem áudio ambiental |
| `quality.json` | Contagens declaradas pelo revisor e vínculo SHA256 com métricas/respostas |
| `selection.json` | Indicação e vínculo SHA256 com métricas/revisão; não altera preferências |

Use **Ver respostas privadas para revisão**. Uma janela separada permite escolher
cada turno e ler pedido/resposta como texto; seu conteúdo não é copiado para o
chat ou executado. Não existe juiz automático de significado. Depois de revisar
todas as respostas, preencha para cada modelo:

- Número de respostas revisadas e número considerado adequado.
- Número de erros críticos observados, incluindo números e negações.
- Número de ocorrências observadas de falta de memória.

Os campos começam vazios. São declarações humanas: a interface não comprova que
alguém leu cada resposta ou observou todo o sistema. As contagens são validadas,
vinculadas aos arquivos exatos e combinadas com os efeitos medidos. Nenhuma nota
é inferida de uma resposta que apenas afirma ter funcionado.

**Registrar revisão e indicar elegível** exige ambos os modelos completos,
respostas arquivadas correspondentes, qualidade ≥95%, zero erros críticos/OOM,
nenhum efeito indevido/duplicado e RAM/PSS completas. Valores não finitos e
identidade de daemon/pesos alterada invalidam a seleção. Entre elegíveis, vence
o menor pior p95 de primeiro texto aquecido entre cenários; empate por pico PSS.
Isso não mede som no fone, acurácia STT ou qualidade geral fora desses pedidos.

## Aplicar com ação explícita

**Copiar elegível para configuração** valida novamente os hashes e a indicação,
consulta a identidade atual dos pesos e recusa divergência. Somente preenche o
modelo na Configuração inicial. Use então **Aplicar perfil Local e modelo
informado**, que reaproveita a troca transacional existente. A indicação não
salva preferências nem concede ferramentas. O digest observado não é um bloqueio
contra troca posterior de pesos por um administrador.

**Abrir ensaio existente sem inferir** permite carregar métricas e repetir a
revisão. Alteração de métricas, respostas ou qualidade invalida uma indicação
anterior. Não edite arquivos para transformar um ensaio parcial em aprovado.

## Evidência e pendências

Os testes controlados cobrem fases frias/aquecidas, dois candidatos, configuração
sem mutação de ambiente, cancelamento durante inferência, limpeza com token
separado, contagens incompletas, erro crítico/OOM, RAM inválida, alteração de
arquivos/pesos e ausência de mudança de preferências. Tk real exercita formulário,
contagens explícitas, Parar com escala maior e respostas privadas fora do chat.
Os provedores usados nesses testes são fixtures, sem comparação de modelos reais.

O ensaio normal tentou instalar Ollama e falhou na consulta oficial. O preflight
da interface recusou a comparação sem daemon/PID, não inferiu nem selecionou
modelo e preservou FCC. Evidência sanitizada em
[model-comparison-preflight-2026-11-06.json](metrics/model-comparison-preflight-2026-11-06.json).

Continuam pendentes daemon/pesos reais, execução dos 396 turnos, revisão humana,
comparação de RAM/latência no notebook e ensaio com internet bloqueada também
para o daemon. Rede isolada e áudio físico permanecem não testados; voz humana,
Jarvis isolado, Kokoro, engenharia FCC real e jornada final seguem no plano.
