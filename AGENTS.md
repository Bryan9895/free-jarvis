# Instruções de desenvolvimento do free-jarvis

## Objetivo do produto

Assistente desktop em português brasileiro para Bryan, no Ubuntu GNOME Wayland. Deve ouvir a chamada **Jarvis**, compreender pedidos sem cronômetro de fala, executar ferramentas autorizadas, verificar o resultado e responder com voz natural. A conversa é a tela principal. Diagnósticos e operações avançadas ficam em configurações.

O relato do usuário sobre falhas reais prevalece sobre uma demonstração com mocks. Não declare voz/autonomia prontas apenas porque a suíte passou.

## Documentos de execução

- Leia `docs/PLANO_JARVIS_AUTONOMO.md` antes de implementar essa evolução.
- Consulte `docs/REVISAO_REFERENCIAS_VOZ.md` para evidências, versões e limites das referências.
- `docs/PROMPT_AGENTE_JARVIS.md` é o briefing executável desta entrega.
- Preserve documentos históricos; marque decisões antigas superadas quando necessário. Este plano descreve trabalho futuro, não funções já entregues.

## Regras de arquitetura

1. Preserve `JarvisService`, FCC, SQLite, `Toolkit`, registro de ferramentas e integrações GNOME. Evolua os adaptadores; evite reescrever o produto inteiro.
2. GUI e CLI devem usar o mesmo controlador de conversa. Widgets não abrem microfone, não chamam FCC diretamente e não executam ferramentas.
3. Uma sessão possui um único dono do dispositivo de captura. Wake word, VAD e diagnóstico recebem áudio pelo coordenador, sem streams concorrentes nem perda silenciosa de quadros.
4. Detecção de ativação, fim de fala, STT, execução e TTS são etapas distintas. Modelo de conversa não é modelo Whisper; nível de áudio não comprova fala compreendida.
5. Não use seis segundos como duração obrigatória de pedido. Um limite técnico de buffer pode segmentar o áudio, mas não finalizar/truncar a intenção sem informar o usuário.
6. “Jarvis” isolado é requisito. Um modelo que só detecta “Hey Jarvis” não satisfaz esse requisito. Valide pronúncia brasileira e documente disponibilidade do detector antes de anunciá-lo como ativo.
7. Controle transições com IDs de sessão/turno, eventos tipados e cancelamento. Ignore resultados atrasados de turnos cancelados; não duplique comandos nem confirmações.
8. Texto para tela e texto para voz são representações distintas. Não leia Markdown, caminhos extensos, JSON ou blocos de código literalmente como resposta comum.
9. Use carregamento tardio/cache limitado para STT/TTS. O alvo tem 8 GB de RAM, CPU e Bluetooth; não exija GPU, nuvem de áudio ou múltiplos modelos Whisper carregados.
10. Falhas de microfone, STT, modelo FCC e saída de áudio precisam ter estados e recuperação independentes. Não confunda 404 NIM com falha de escuta.

## Autonomia e comportamento

- Execute instruções claras pelas ferramentas existentes, sem substituir a ação por um tutorial. Faça perguntas apenas quando faltar uma informação que muda a ação.
- Preserve autorizações existentes e permissões nativas. Autonomia não é afirmar efeitos sem observá-los nem contornar permissões do desktop.
- Só diga “concluído” com evidência de resultado; diferencie pedido enviado, efeito verificado e efeito incerto. Preserve cancelamento, loop guard e histórico.
- Não repita ações com efeitos após falha de rede sem saber se já aconteceram. Fallback de provedor segue a política configurada e fica visível.
- Personalidade: direta, calma, cordial, competente, sem saudações repetidas, uso insistente do nome Bryan ou narração de símbolos. Nunca invente estados de humor, consciência ou acesso que não existem.

## Interface

- Início: indicador de estado real, transcrição/conversa, campo de texto, microfone/mudo, parar e acesso a configurações.
- Configurações: Voz, Microfone, Modelo de conversa, Diagnósticos e Avançado. Tarefas, planos, janelas e métricas continuam acessíveis, sem ocupar permanentemente a tela inicial.
- Sem animação que finja captura ou execução; forma de onda, se existir, usa medidas reais.
- Preserve Tkinter inicialmente. Registre uma decisão com custos e protótipo validado antes de qualquer migração de toolkit.

## Verificação e entrega

- Rode a suíte adequada à mudança: `PYTHONPATH=src python -m unittest discover -s tests -q`; use display real/virtual para mudanças de GUI, além de `git diff --check`.
- Teste jornadas completas e erros, além dos componentes. Registre separadamente: teste automatizado, ensaio com áudio gravado e ensaio físico Bluetooth/FCC/GNOME.
- Registre latência por etapa, taxa de ativações corretas e falsos positivos. Metas no plano são critérios futuros, nunca resultados já medidos.
- Sem áudio/transcrições ambientais em logs persistentes por padrão. Dados de avaliação consentidos ficam fora do git; métricas sanitizadas podem ser versionadas.
- Ao faltar hardware/credencial, implemente e valide o que for possível e mantenha o aceite físico explicitamente pendente. Não invente uma validação.

## Git e referências

- O usuário autorizou publicar cada alteração concluída na branch **main**, inclusive pequena. Faça commits pequenos, verificáveis, sem pedir novamente autorização para esse envio.
- Confira o remoto antes de publicar; preserve alterações alheias. Não faça force push. Use a integração GitHub quando push por shell não estiver disponível.
- Mark-LVI: referência de experiência/arquitetura sob CC BY-NC 4.0. Escreva código e assets próprios; não importe seu avatar, identidade, arquivos ou implementação.
- OpenJarvis: referência modular sob Apache-2.0. Não adicione seu framework inteiro como dependência para copiar uma abstração; eventual reutilização de código exige os avisos aplicáveis.
- Não instale dependências das referências nem execute seus scripts de setup só para analisá-las.
