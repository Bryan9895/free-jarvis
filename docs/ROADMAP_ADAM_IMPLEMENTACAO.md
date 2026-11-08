# Roteiro de evolução ADAM — quadro de aceite (08/11/2026)

| Marco | Estado no código | Aceite físico |
|---|---|---|
| M1 — Instalar Ubuntu Python sem PEP 668 | `tools/install_ubuntu.sh` + testes | Pendente no Ubuntu do usuário |
| M2 — GUI Tkinter/Canvas | Esfera, configurações e avisos | Pendente no Wayland real |
| M3 — Whisper + FCC + ElevenLabs | Pipeline de voz modular | Pendente credenciais, rede e Bluetooth |
| M4 — “Adam”/conversa sem botão | Fallback por transcrição + VAD; detector ONNX precisa modelo treinado | **Pendente** wake robusto |
| M5 — Latência | Streaming por frase; medidor de primeiro texto/total na GUI | Pendente baseline p50/p95 físico |
| M6 — Personalidade/memória/modelos | Personalidade em arquivo e modelos editáveis; SQLite legado preservado | Pendente UX completa de memórias |
| M7 — Automação desktop | Toolkit/autorizações conservados; diálogo Tk de aprovação | Pendente ensaio Wayland real |
| M8 — Multiagentes de engenharia | Orquestrador `adam-team` com Supervisor→Desenvolvedor→Codex crítico→testes→commit/branch opcional | Pendente executar provedores FCC-CLAUDE e Codex CLI reais |
| M9 — Hardware | `RobotTransport`/simulador, protocolo v1 | Pendente Orange Pi/ESP32, testes elétricos |

## Aceite de ponta a ponta

1. `bash tools/install_ubuntu.sh` (sem root pip).
2. `adam --gui --text-only` → abre, permite enviar texto ao FCC e mostrar resposta.
3. `adam --gui` → ativa áudio, escuta e transcreve “Adam, ...”.
4. Primeiro delta aparece e ElevenLabs fala em fone Bluetooth.
5. Esfera reage ao RMS do microfone e ao envelope do WAV sintetizado.
6. Após resposta, escuta retorna; pressionar Segure para falar interrompe fala anterior.
7. Nenhuma ferramenta executa ações sensíveis sem autorização correspondente.
8. Registrar latências p50/p95 e verificar comportamento sem rede/chave.

**Limites de validação:** ações do GitHub provam apenas CI remoto.
Nenhuma chamada FCC real, chave ElevenLabs ou hardware foi disponibilizado
ao runner. Não confundir testes simulados com aceitação do minirrobô.
