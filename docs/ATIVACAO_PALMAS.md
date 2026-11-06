# Palmas: continuidade do áudio e turno único

Checkpoint de 05/11/2026, sobre `ef1f1064e0d14da865a4a0757ba4b85fc56b3934`.

Foi corrigida a dependência da posição da palma dentro do bloco de captura.
O detector anterior examinava cada bloco isoladamente e exigia quietude antes
e depois do impulso no mesmo bloco. Uma palma dividida na fronteira podia ser
perdida ou iniciar VAD antes de completar a decisão de ativação.

## Fluxo implementado

O detector recebe o PCM16 mono a 16 kHz já normalizado pelo fluxo existente.
Mantém uma janela limitada de até 160 ms e os critérios de pico, duração curta e
quietude. A janela atravessa fronteiras de blocos. O debounce de 1,5 s usa o
timestamp do áudio capturado, evitando confundir atraso de processamento com
intervalo entre palmas.

Enquanto o fallback STT aguarda ativação com palma habilitada, um bloco fica
reservado antes do VAD, normalmente 80 ms. Isso dá tempo para decidir um impulso
que terminou na fronteira antes de classificá-lo como início de fala. Ao começar
a fala ou desabilitar a palma, a reserva é liberada em ordem, sem eliminar
amostras. O timestamp do bloco reservado é preservado. A reserva não existe
durante a fala já iniciada ou no caminho de palavra acústica dedicada.

Após detectar a palma, o impulso deixa o pré-áudio; a cauda posterior é preservada
para o pedido. A GUI recebe a solicitação de exibição pelo evento já existente,
e a captura aguarda um único pedido completo. Após execução/resposta, volta à
ativação. O texto de estado não anuncia uma janela de seguimento que a palma
não abriu. A chamada Jarvis e o botão de falar continuam disponíveis.

Desabilitar a detecção ou iniciar uma nova captura limpa o histórico parcial;
o debounce permanece entre turnos do mesmo listener. Pausa/cancelamento no fim
da captura descarta o resultado antes de permitir transcrição/execução tardia.
O detector continua compartilhando a captura única; não abre outro dispositivo
ou stream paralelo. Não há gravação de áudio ambiental para logs.

## Validação automatizada

Os testes usam PCM e transcrição controlados, sem microfone físico:

- Um impulso sintético em cada uma das 1.280 posições possíveis do bloco,
  incluindo impulsos divididos, produz exatamente uma ativação.
- Silêncio, tom e ruído sustentado não ativam nos casos sintéticos existentes.
- Desabilitar a detecção limpa um impulso parcial; a reserva é liberada sem
  perda e mantém o timestamp original.
- Uma jornada do listener recebe palma dividida, preserva o início inteiro do
  pedido, envia um comando sem exigir Jarvis e volta à espera de ativação.
- O caminho fallback sem palma conserva o primeiro bloco da fala; pausa na
  saída do stream invalida o áudio antes da entrega.
- A jornada observa no máximo um stream aberto e apaga o WAV temporário.

Esses resultados comprovam continuidade/estado com entradas controladas, não a
taxa de detecção de pessoas reais, nem rejeição de teclado, batidas ou som no fone.
A janela/reserva acrescenta espera limitada na ativação do fallback; a latência
física ainda precisa ser medida no hardware alvo.

## Uso e aceite físico pendente

Palma continua experimental e desativada por padrão. Para usar, inicie uma sessão
visível, configure entrada/saída e habilite a opção em Configurações → Voz.
O aplicativo fechado ou a escuta parada não detecta palmas. Execução, resposta
falada e mudo mantêm as proteções de captura existentes.

O lançador `jarvis-show` reaproveita a instância gráfica. O compositor Wayland
decide se concede foco; o evento confirma solicitação de exibição, não foco
garantido. Não houve mudança de permissões GNOME ou concessões de ferramentas.

Ainda falta ensaiar palmas deliberadas, batidas, teclado, ruído, fala, áudio do
Jarvis e palmas repetidas no Bluetooth, com as mesmas permissões e sem internet
após provisionamento. Faltam Kokoro real, chamada Jarvis isolada e os turnos físicos
finais. Nenhum áudio humano foi capturado ou reproduzido neste checkpoint.
