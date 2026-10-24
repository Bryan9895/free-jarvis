# Prompt único — free-jarvis rápido, autônomo e conversacional

Você é o engenheiro sênior responsável por evoluir `Bryan9895/free-jarvis`. Sua prioridade principal é **reduzir o tempo entre o fim da fala do usuário e a primeira resposta útil, visual ou falada**, preservando compreensão, execução verificada, estabilidade e privacidade. Implemente e valide as melhorias; não entregue somente sugestões ou uma nova documentação.

Esta especificação é independente dos prompts anteriores. Leia as instruções aplicáveis do repositório, especialmente `AGENTS.md`, e confronte esta análise com o código atual. Atualize o AGENTS sem apagar regras válidas. O usuário já autorizou publicar cada alteração concluída na branch **main**, mesmo pequena. Faça commits pequenos e verificáveis, confira alterações remotas antes de publicar e não faça force push. Não peça novamente autorização para esse envio.

## 1. Contexto, objetivo e prioridades

Ambiente: Ubuntu GNOME Wayland, CPU, 8 GB de RAM, fone Bluetooth, FCC como gateway de modelos, Tkinter, SQLite e ferramentas locais. Whisper small apresentou reconhecimento melhor que base no teste relatado. Não troque silenciosamente por tiny/base nem exija GPU para conseguir um número de latência menor.

Experiência desejada: iniciar Jarvis, dizer **Jarvis** seguido do pedido, falar sem cronômetro obrigatório, terminar com aproximadamente um segundo de silêncio, receber uma resposta natural e continuar a conversa. Pedidos claros e autorizados devem executar ferramentas e verificar efeitos, sem respostas que apenas ensinem o usuário a fazer a ação. Um botão de falar é alternativa, não requisito.

Ordem de prioridade:

1. **P0: latência real e percebida**, diagnóstico do caminho crítico, primeiro texto/áudio úteis, cancelamento e recuperação de espera.
2. **P1: confiabilidade da conversa**, ativação, precisão da transcrição, continuidade, ações e voz natural.
3. **P2: ergonomia e consolidação arquitetural**, preservando a interface simples e evitando outra reescrita antes de medir a melhora.

Uma animação, “já vou responder” ou bip não contam como resposta útil. Não retirar verificação, cortar pedidos, omitir erros ou antecipar uma conclusão para parecer rápido.

## 2. Base auditada e melhorias que já existem

Revisão estática em 23/10/2026 sobre `cd08fa21883a721ab7d3fa27fb03330b3e27bfb4`, obtido da main. Atualize o SHA antes de implementar se houver novos commits.

Já existem e devem ser preservados:

- Endpoint compartilhado entre botão e contínuo; silêncio configurável, pré-fala, rejeição de overflow/turno incompleto e timeout de espera separado da fala ativa. Os antigos cortes obrigatórios de 6/15 segundos foram corrigidos no caminho normal. Diagnóstico pode continuar com amostra fixa claramente rotulada.
- Normalização de captura negociada, VAD Silero, cache único de Whisper CPU/int8 e Piper residente em processo cancelável.
- Instalação verificada da voz pt-BR pela interface, seleção de saída, preferências persistentes e reconexão limitada.
- `ConversationController`, eventos com sessão/turno, descarte de respostas atrasadas, representação separada para tela/fala e persona nas instruções.
- Serviço, ferramentas e SQLite preservados; GUI com configurações recolhidas, worker de áudio/configuração independente da rede FCC e recuperação do polling Tk após evento inválido.

O último checkpoint documentado registra **425 testes**, com ensaio gráfico, e aceite físico ainda pendente. Esse é um resultado histórico, não uma execução feita nesta revisão. Não copie números antigos como validação nova. `docs/VALIDACAO_CONVERSA.md` registra síntese controlada de uma frase com Piper em 3,739 s na primeira chamada e 0,234 s na segunda: isso demonstra diferença de carga fria, não latência ponta a ponta ou som audível no fone.

## 3. Achados atuais: o que precisa ajustar

| Prioridade | Evidência no snapshot | Ajuste necessário |
| --- | --- | --- |
| P0 | `FCCClient.responses`, em `fcc.py`, recebe SSE, mas descarta deltas para os consumidores e só retorna a resposta concluída. O protocolo `ModelProvider` também expõe apenas resposta completa. | Streaming efetivo até a apresentação, com API compatível e sem quebrar ferramentas. |
| P0 | O parser continua lendo depois de `response.completed`, até EOF ou `[DONE]`. Replay local controlado confirmou essa leitura adicional; nenhum atraso de servidor foi medido. | Encerrar o consumo no evento terminal válido, validando o contrato do FCC e fechando recursos. Um servidor que mantenha a conexão não pode prender o turno. |
| P0 | `ConversationController.run` espera `service.ask` terminar, então mostra o texto e chama `voice.speak`. | Diminuir a espera serial e disponibilizar conteúdo útil antes da conclusão total quando for correto. |
| P0 | `VoiceIO.speak` sintetiza um chunk inteiro, grava WAV, reproduz e só então sintetiza o seguinte. `speech_chunks` aceita até 700 caracteres por chunk; Piper já é residente. | Início de voz por frase curta e pipeline limitado entre síntese/reprodução. Medir antes de trocar cache/processo já existentes. |
| P0 | Cliente FCC tem timeout de 100 s; fallback percorre candidatos sequencialmente. Cancelamento do agente é verificado antes/depois da chamada, não interrompe a leitura SSE em andamento. | Deadline total por turno, tempos de conexão/primeiro evento/inatividade e cancelamento do transporte, com retentativas limitadas. Timeout de socket não é deadline total. |
| P0 | Ativação continua via Whisper sobre uma fala inteira, seguida de regex inicial. A própria UI avisa que é fallback. | Detector local de “Jarvis” separado do STT, com artefato e avaliação pt-BR; retirar transcrição completa da espera por ativação quando validado. |
| P1 | STT usa `beam_size=5`, VAD interno e um lock de cache durante a transcrição. VAD de captura também já foi aplicado. | Medir carga fria/aquecida, custo de decoding, segunda passagem VAD e contenção. Otimizar sem degradar reconhecimento ou carregar vários modelos. |
| P1 | `SileroActivity` reavalia janela de até 512 ms em cada bloco; o adaptador de captura recria objetos de turno e abre/fecha streams. | Medir CPU e custo por bloco; reutilizar recursos seguros e avaliar VAD incremental por API estável. Não presumir que os pesos sejam recarregados em cada chamada. |
| P1 | Agente manda instruções gerais extensas em todas as rotas, até 4/10 mensagens de histórico e catálogo conforme o roteador. Admite até seis rodadas de ferramentas mais conclusão. | Orçamento de contexto, catálogo mínimo correto e menos rodadas redundantes. Não confundir limite máximo com rodadas sempre executadas. |
| P1 | Resposta local pós-ferramenta já existe para foco, estado de janela e layout; outros casos podem precisar de nova inferência. | Ampliar respostas determinísticas apenas para resultados simples, suficientes e verificados. Preservar pedidos compostos. |
| P1 | `reasoning.effort=none` só é enviado para Ollama; outros provedores mantêm política própria. Não há ranking medido de latência/capacidade. | Perfis de inferência por capacidade efetivamente suportada, sem enviar parâmetros universais nem escolher modelo só por ser grande/pequeno. |
| P1 | Já há métricas do agente e quadros, mas falta uma trilha ponta a ponta de captura até primeiro áudio e medição de 30 turnos reais. | Spans correlacionados para filas, STT, provedor, ferramentas, síntese, reprodução e percepção. |
| P1 | Inventários, verificação de janela, navegador e seleção de catálogo têm consultas/esperas próprias. | Separar tempo externo de custo evitável; cachear metadados seguros, reaproveitar observações válidas e interromper polling assim que houver evidência. |
| P2 | Estado canônico começa na intenção textual; captura/ativação ainda têm lifecycle legado. Detector acústico e segmentação acima do teto seguem pendentes. | Consolidar IDs e estados desde a captura, depois do primeiro ganho medido, sem criar um segundo executor. |

Achado estático é evidência de fluxo/custo potencial, não prova de qual etapa domina o notebook. Não atribua toda demora ao Whisper ou ao modelo sem medição.

## 4. Etapa inicial obrigatória: medir a demora certa

Antes de otimizar, instrumente o fluxo real com relógio monotônico e `session_id`, `turn_id`, `request_id`, tentativa e rodada. Eventos de captura anteriores à intenção precisam de correlação posterior. Não reutilize IDs cancelados.

Marque, no mínimo:

- último áudio de fala, endpoint decidido e fila de transcrição;
- início/fim da carga STT e da transcrição;
- intenção enfileirada, retirada da fila e aceita pelo controlador;
- início da requisição FCC, primeiro evento, primeiro delta de texto útil, primeira frase utilizável e resposta final;
- início/fim de cada ferramenta e da observação/verificação;
- início/fim da carga TTS, síntese da primeira frase, player pronto, primeiros frames enviados e fim da reprodução;
- pedido de cancelamento, interrupção efetiva e liberação da captura.

Defina as métricas sem misturar relógios de máquinas diferentes:

- **Endpoint:** último frame de fala → decisão de término. Separar intervalo de silêncio configurado do atraso extra de processamento.
- **Resposta visual:** fim da fala → primeiro texto útil exibido. Para teclado, medir Enviar → primeiro texto útil separadamente.
- **Resposta de voz:** fim da fala → primeiro áudio útil no dispositivo, quando observável. Início do processo player não comprova que o fone já tocou; usar proxy identificado e ensaio físico para o aceite.
- **Conclusão de ação:** fim da fala → efeito observado. Uma confirmação de recebimento não é conclusão.
- **Cancelamento:** clique/controle Parar → interrupção efetiva do trabalho/áudio e ausência de efeitos posteriores indevidos.

Registre p50, p95, pior caso, número de amostras, falhas e cancelamentos. Não some percentis independentes como se fossem o percentil ponta a ponta. Separe tempo frio, download, rede, fila e execução aquecida. Métricas persistidas devem ser sanitizadas, sem áudio, prompts completos, tokens ou fala ambiental por padrão.

Crie um benchmark repetível com perguntas curtas, respostas longas, ação simples, ação composta e falhas de rede/voz. Faça pelo menos 30 turnos representativos, reportando N de cada classe; amplie a amostra por classe antes de tratar p95 como estável. Compare mesmo hardware, modelo, endpoint e entradas, alternando antes/depois quando possível. Registre consumo de CPU/RSS, perdas e tamanho das filas. Sem credenciais/fone, execute testes controlados e mantenha o benchmark real pendente.

## 5. Implementação P0 — tirar esperas evitáveis do caminho crítico

### 5.1 Streaming verdadeiro, respeitando o protocolo

Evolua `FCCClient`, `AutoModelClient`, `ModelProvider`, `Agent`, `JarvisService`, controlador e GUI/CLI para eventos incrementais. Preserve `responses()` ou adaptador equivalente para consumidores que exigem resultado completo.

Trate SSE fragmentado, eventos multilinha, UTF-8, ferramentas/argumentos parciais, falha, incomplete, EOF e terminal. Depois de um terminal válido, valide o resultado e encerre a leitura sem esperar a conexão fechar. Não executar uma ferramenta com JSON de argumentos ainda incompleto. Não persistir a mesma mensagem por delta: consolidar uma vez no fim do turno.

Para perguntas informativas, exiba deltas e produza uma primeira frase coerente assim que possível. Para rodadas que podem chamar ferramentas, não anuncie “feito” antes da observação; bufferize narrativa incerta e use estados reais de progresso. Não leia raciocínio interno, argumentos de ferramentas ou conteúdo parcial inválido. O caminho síncrono continua funcionando para provedores sem suporte validado ao fluxo incremental.

### 5.2 Voz em pipeline, com baixa latência de primeira frase

Use o Piper residente já entregue. Segmente sentenças completas com tamanho inicial pequeno, respeitando abreviações, números, links e código. Evite esperar 700 caracteres para falar, sem produzir sílabas ou frases sem sentido.

Separe produtor de síntese e consumidor de reprodução com fila pequena, ordem garantida e backpressure. Enquanto a primeira frase toca, a próxima pode ser preparada se houver benefício medido na CPU disponível. Não concorrer cegamente Whisper, Piper e ONNX com todos os núcleos. Medir número de threads e RAM antes de escolher parâmetros.

Reutilize a saída de áudio quando viável e valide se abrir um player por chunk custa tempo ou produz lacunas. Não sintetizar duas vezes o mesmo trecho na passagem streaming → final. Cancelamento invalida chunks antigos e encerra/recolhe subprocessos. Falha de TTS preserva o texto e nunca reexecuta ferramentas.

### 5.3 Deadlines, falhas rápidas e cancelamento real

Distinguir timeout de conexão, espera pelo primeiro evento, inatividade entre eventos e deadline absoluto do pedido. Usar valores configuráveis e calibrados, com mensagem de erro recuperável; reduzir timeout sozinho não é otimizar uma resposta bem-sucedida.

O botão Parar deve interromper leitura HTTP, geração/síntese/reprodução quando suportado, e descartar resultados atrasados. Não deixar um lock ocupado por uma requisição cancelada por 100 segundos. Feche sockets e workers sem bloquear Tk.

Limite tentativas dentro de um orçamento total. Um stream que já mostrou/falou conteúdo não pode recomeçar silenciosamente com outra resposta. Se houve ferramenta, reconciliar o efeito antes de qualquer repetição. Fallback entre provedores respeita configuração e fica visível. Não varrer todo catálogo nem fazer benchmark de todos os modelos em cada startup.

## 6. Implementação P1 — compreensão rápida e menos inferências

### 6.1 STT, VAD, wake word e entrada Bluetooth

- Preserve Whisper small/int8 como referência inicial de qualidade. Compare beam 5/3/1 ou outro ajuste permitido em um corpus consentido pt-BR com nomes, números, negações e pedidos de ação. Só adote perfil rápido se a precisão e a taxa de conclusão se mantiverem; não esconda erro para conseguir velocidade.
- Meça a passagem VAD do Whisper sobre áudio já segmentado. Avalie reaproveitar segmentação ou reduzir trabalho repetido, mantendo detecção de incerteza/ruído. Não desative VAD/confiança sem teste.
- Warm-up opcional de STT/TTS deve ocorrer fora da thread GUI, sem download automático bloqueante nem competição com o primeiro pedido. Cache limitado, uma voz/modelo quando possível, troca explícita e persistência consistente.
- Avalie contenção do cache entre diagnóstico e fala, construção repetida de objetos, WAV/resampling e pausas de captura. Prefira memória quando trouxer ganho medido, com interfaces compatíveis e limpeza. Não reescrever todo áudio apenas para eliminar arquivos pequenos sem perfil.
- Detector acústico “Jarvis” isolado continua pendente. Avaliar artefato local leve, licença/hash e pronúncia brasileira. O modelo `hey_jarvis` do Mark não comprova suporte a “Jarvis” isolado. Exibir fallback honesto enquanto não houver um detector validado.
- Pré-fala deve preservar início do comando após ativação. Endpoint inicial de aproximadamente 1 s; não baixar para 200 ms e cortar pausas naturais. Uma pausa de 800 ms deve ser preservada na configuração de 1 s.
- Fonte SoundDevice, PipeWire/Pulse e saída Bluetooth precisam ser confirmadas separadamente. Uma única captura, formato negociado e normalização sem duplicação. Reconexão limitada e perda explícita, sem enviar frase incompleta.
- Teto emergencial de 120 s permanece proteção; futura segmentação/remontagem deve manter intenção pendente, não executar uma versão truncada. Timeout de espera só vale antes de a fala começar.

### 6.2 Modelo de conversa e contexto

- Meça TTFT, primeira frase, duração total, falhas e capacidade de ferramentas por modelo realmente disponível. Separe perguntas de ações. Mantenha o modelo preferido e política de provedor; perfil de velocidade é configurável, transparente e persistente.
- Trate `reasoning`, orçamento de saída e opções de decoding por capacidade validada do provedor. Não assumir que `effort=none` funciona para todos. 512/1536 tokens são tetos atuais, não consumo obrigatório: reduzir só o teto não prova ganho e pode gerar incomplete.
- Preserve regras de execução e dados não confiáveis, mas evite enviar instruções de todas as operações para uma pergunta simples. Use contexto relevante e orçamento de tokens, sem uma segunda chamada LLM para escolher o que enviar.
- Catálogo de ferramentas mínimo correto, sem retirar ferramentas necessárias de pedidos compostos. Reaproveitar registry/roteador existentes. Resolução não concede permissões.
- Resumos de memória ou cache devem ter orçamento e política de invalidação. Nunca cachear como verdade foco/posição de janela, arquivos que mudaram, resultado de ação, saúde permanente de modelo ou dados atuais sem verificação.

### 6.3 Autonomia com menos rodadas e verificação preservada

- Medir quantas inferências acontecem por intenção. Uma pergunta curta não precisa de planejamento ou ferramentas só para responder.
- Ampliar respostas locais de resultado somente para ações simples com evidência suficiente. Se o pedido inclui próximos passos, não encerrar no primeiro sucesso.
- Não repetir inventários/observações equivalentes dentro de um passo sem necessidade. Validade temporal importa, especialmente depois de aprovação e de mutação. Não eliminar a revalidação necessária para ganhar tempo.
- Trocar esperas fixas por observação que termina assim que o estado desejado é confirmado. Manter deadline e custo controlado para GNOME/navegador. Aplicativo lento é dependência externa, não motivo para inventar conclusão.
- Use o executor, loop guard e cancelamento existentes; não criar um segundo executor de voz. Pergunte apenas por ambiguidade material, dado ausente, transcrição duvidosa que altere o efeito ou autorização realmente exigida.

## 7. Conversa, interface e pendências de confiabilidade

Preserve a tela inicial simplificada: conversa/transcrição, estado real, campo de texto, microfone/mudo, Parar e Configurações. Voz, microfone, modelos, diagnósticos e opções avançadas ficam recolhidos. Não reintroduza dez painéis fixos nem migre de Tkinter antes de demonstrar uma limitação e um protótipo superior.

Mostre imediatamente o estado real e o motivo de uma espera relevante. Um único aviso curto após um limiar pode orientar o usuário, sem repetir “aguarde” nem preencher silêncio com frases artificiais. A interface pode mostrar diagnóstico por etapa em configurações, não tempos ou métricas fictícios no HUD.

Preserve a proteção do polling Tk. Evite uma tarefa `after` por token e filas crescentes: coalesça atualizações visuais mantendo texto íntegro e preservando eventos de erro, conclusão e cancelamento. A resposta deve atualizar progressivamente sem travar cliques.

Persona: português brasileiro, direta, calma, cordial, respostas curtas para perguntas curtas. Não repetir “Olá Bryan”, o nome do usuário, perguntas de cortesia ou símbolos Markdown. Preserve `display_text/spoken_text`; JSON/código/tabelas ficam na tela com resumo falado apropriado. Voz pt-BR selecionada deve sobreviver ao reinício; testar saída, instalar voz e recuperar falha não dependem do FCC.

Concluir correlação e estados desde a captura, preservando workers e ownership de áudio. Manter reconexão, preferências/ambiente, fallback visível e ausência de autoeco. Primeiro garantir conversa sequencial e Parar; interrupção por voz durante TTS exige detecção/eco e ensaio físico próprios. Não anunciar barge-in antes desse aceite.

Mark-LVI (`https://github.com/FatihMakes/Mark-LVI`) é referência de HUD, cadeia de voz e configurações recolhidas; não copiar código/assets sob CC BY-NC. OpenJarvis (`https://github.com/open-jarvis/OpenJarvis`) inspira separação de responsabilidades e resolução de ferramentas; não importar seu framework inteiro para otimizar esta aplicação. O núcleo FCC/SQLite/Toolkit/GNOME permanece.

## 8. Metas e matriz de testes

Metas iniciais propostas, não resultados medidos nem garantia de desempenho:

| Métrica | Alvo inicial em ambiente de referência |
| --- | --- |
| Feedback visual de comando/clique aceito | p95 até 150 ms, sem bloquear GUI |
| Endpoint com silêncio configurado em 1 s | p95 até 1,5 s após fim da fala em ambiente limpo |
| Primeiro áudio após primeira frase utilizável | p95 até 1 s com voz aquecida; distinguir síntese, player e som físico |
| Primeira resposta útil falada a pergunta curta | objetivo p50 até 3 s / p95 até 6 s após fim da fala, medido com modelo/rede identificados |
| Ganho ponta a ponta | buscar pelo menos 30% sobre baseline equivalente, sem piorar qualidade/falhas; informar quando o ganho externo não for controlável |
| Parar | feedback p95 até 150 ms e liberação do trabalho cancelável p95 até 500 ms; registrar limitações reais do transporte/dispositivo |
| Estabilidade | 30 turnos sem crescimento contínuo de fila/RSS, streams duplicados ou execução de resultados cancelados |

Se os alvos não forem viáveis no notebook/modelo escolhido, mostre a decomposição, o melhor resultado comprovado e o ajuste necessário. Não trate uma meta como fato nem declare reprovação do usuário por sua conexão. Baixar a mediana enquanto o p95, a precisão ou os erros pioram não é aceite.

Testes obrigatórios:

1. SSE com deltas antes do final, fragmentação, resposta final mantida aberta, erro/incomplete/EOF, tool args parciais e cancelamento. Provar que o fluxo chega à GUI/voz, sem duplicações ou sucesso prematuro.
2. Pergunta curta, resposta longa, pergunta digitada e falada, ação simples/composta, autorização/ambiguidade e modelo lento/404/429. Sem replay de efeitos nem fallback oculto após conteúdo já emitido.
3. Fala de 3/10/25/60 s, pausa de 800 ms, ruído, silêncio, overflow, queda de Bluetooth e limite emergencial. Nenhuma melhora pode trazer de volta o corte obrigatório em 6 s.
4. Qualidade STT antes/depois com mesmo áudio consentido: erro por palavra, intenção correta, números/negações, falsos comandos e tempo. Registrar tamanho do conjunto e limites da avaliação.
5. TTS frio/aquecido, primeira frase, lacunas entre chunks, texto longo/Markdown e cancelamento. Sem dizer “asterisco”, duplicar frase ou anunciar resultado não observado.
6. Detector isolado “Jarvis”: pelo menos 18/20 ativações no fone e no máximo uma falsa ativação em 30 min negativos, com condições registradas. É gate de amostra, não garantia universal; sem artefato validado, manter pendente.
7. GUI/CLI, preferências e startup offline, polling com evento inválido, Configurações, 1040×640 e 1366×768, escala GNOME e contabilidade de filas/CPU/RSS. Nenhum benchmark de foco deve concorrer com outro no mesmo display.

Rode `PYTHONPATH=src python -m unittest discover -s tests -q` e `git diff --check`, além dos testes focados. Separe automação, áudio sintético, áudio humano consentido e ensaio físico. Atualize `docs/VALIDACAO_CONVERSA.md` e produza um relatório de latência reproduzível com antes/depois, configuração, amostras, regressões e pendências. Não versionar áudio ambiental, segredos ou textos privados do benchmark.

## 9. Ordem de trabalho e definição de conclusão

1. Sincronizar main, auditar o fluxo atual e obter baseline ponta a ponta.
2. Instrumentar/correlacionar etapas, filas e cancelamento sem mudar comportamento.
3. Corrigir término SSE e deadlines; entregar streaming visual informativo mantendo caminho síncrono compatível.
4. Entregar primeira frase falada e pipeline TTS limitado; validar cancelamento/eco e sem duplicações.
5. Medir/otimizar STT/VAD/cache e modelos/contexto, uma variável por experimento.
6. Reduzir rodadas desnecessárias de ferramentas e espera de verificação com evidências preservadas.
7. Avançar wake word e estados de captura; manter gates acústicos explícitos.
8. Consolidar interface/persona/preferências e executar benchmark de regressão e jornadas físicas.
9. Publicar cada incremento concluído na main, com testes, limitações e documentação. Não parar em promessas de otimização ou em um widget demonstrativo.

Não implementar uma reescrita gigantesca antes do primeiro ganho medido. Não executar arbitrariamente todas as etapas em paralelo, pois precisam de comparações e checkpoints.

A entrega final apresenta commits, gargalos encontrados e percentuais reais por cenário, p50/p95 com N, tempo até primeiro texto/áudio, duração total, qualidade STT, ferramentas/rodadas, CPU/RSS, cancelamento e pendências físicas. Comprove **chamar Jarvis → falar livremente → receber resposta útil cedo → executar/verificar quando necessário → ouvir voz natural → continuar**, com recuperação após falha.

Se o ambiente não permite microfone, áudio audível, GNOME ou credenciais, implemente e valide o que for possível e entregue o procedimento exato para esses aceites. Não afirmar que o Jarvis ficou rápido no notebook sem medir nele, e não declarar o produto final aceito apenas pela suíte de testes.
