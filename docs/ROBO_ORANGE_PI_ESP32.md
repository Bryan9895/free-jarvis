# ADAM · Contrato inicial de hardware (Orange Pi + ESP32)

Este marco **não instala nada no robô**. Ele separa o núcleo de IA da
camada de transporte e define `RobotPacket` e `RobotTransport`, permitindo
testar a comunicação com `SimulatedRobot` sem motores ou sensores.

- **PC / Orange Pi Linux**: interface desktop opcional, VAD, ASR, FCC/modelo
  escolhido pelo usuário, ElevenLabs (serviço remoto), execução de tarefas.
- **ESP32**: microcontrolador dedicado a LEDs, sensores, botões e
  periféricos. A IA e a GUI *não* serão executadas no ESP32.
- **Conexão futura**: cabo serial USB. Não habilitar porta, motores,
  atuadores ou rede sem pareamento e permissões explícitas.
- **Protocolo v1**: objetos JSON UTF-8 em linhas delimitadas por `\\n`;
  no máximo 512 bytes; comandos iniciais `ping`, `status`, `led` e
  `sensor_read`. Sem motores nesta fase.
- **Próximos critérios**: CRC/framing, autenticação local, heartbeat,
  watchdog de atuadores, limite de potência, reconexão, testes elétricos
  e dispositivo físico. São etapas **pendentes**.

Ollama é opção de inferência local e não é obrigatório para FCC.
ElevenLabs continua precisando de rede. Para ficar totalmente offline,
será necessário um TTS local novo ou licenciado.
