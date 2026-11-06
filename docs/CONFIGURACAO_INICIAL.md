# Configuração inicial pela interface

Checkpoint de 06/11/2026 sobre `2c7e93026dd0dd08a770902c08d67286871a61b6`.
O fluxo reúne preparação Local e acesso aos testes de áudio existentes. Não
constitui aceite de inferência offline, ferramentas ou Bluetooth.

Abra `jarvis-fcc --gui` e entre em **Configurações → Configuração inicial**.
O painel possui rolagem e continua disponível quando o provedor de conversa
falha. Abrir o painel não instala arquivos, infere, grava ou reproduz áudio.

## Preparar e usar

1. **Preparar motor Local.** Reutiliza o instalador OpenJarvis fixado e seu
   ambiente isolado. Requer `uv` e Python 3.10–3.13 já instalados; o seletor permite
   escolher o interpretador. Campo vazio procura Python 3.13 no cache do uv.
   A opção de cache limita somente esta instalação. Não instala Python/uv nem
   altera pacotes do sistema ou solicita administração.
2. **Instalar Ollama.** Reutiliza o provisionamento Linux por usuário, release
   estável oficial e verificação SHA256. Este instalador `.tar.zst` requer
   Python 3.14+, enquanto o motor isolado usa seu interpretador compatível.
   O download pode ser grande; falhas mantêm a seleção anterior.
3. **Iniciar servidor Local.** Inicia Ollama sem terminal, com CPU, um modelo
   carregado e uma inferência paralela, diretório próprio e `OLLAMA_NO_CLOUD=1`.
   A prontidão exige porta pertencente ao PID iniciado e resposta de versão.
   Proxies e redirects não são usados na consulta de prontidão.
4. **Baixar modelo informado.** Solicita o pull explicitamente ao daemon local
   e registra a identidade/digest observado pelo motor. Esse comando também
   existe na CLI; ambos usam o mesmo helper. Nome vazio ou remoto é recusado.
   Não escolhe outro candidato nem inicia comparação automaticamente.
5. **Testar inferência textual Local.** Usa o modelo informado e o runtime
   preparado mais recente. O teste é cancelável, não contém ferramentas, rejeita
   chamadas de ferramenta na resposta e não reproduz áudio. Uma resposta textual
   não prova isolamento externo ou qualidade suficiente para selecionar o modelo.
6. **Aplicar perfil Local e modelo informado.** Usa a troca transacional já
   existente, preparando a nova sessão antes de substituir a atual. Lê o ponteiro
   gerenciado atualizado sem exigir reiniciar após instalar o motor. Falha de
   preparação/gravação ou cancelamento recebido durante a preparação preserva
   a sessão anterior. Variáveis explícitas de ambiente têm precedência.
7. **Preparar pesos Whisper.** Reutiliza o download explícito da CLI. A seleção
   no painel serve apenas ao provisionamento; o modelo de reconhecimento em uso
   continua sendo escolhido e salvo em Voz. Não carrega Whisper para transcrever.
8. **Configurar e testar microfone e voz.** Abre o painel Voz existente para
   selecionar entrada/saída, salvar preferências, instalar Piper ou Kokoro e
   executar os testes explícitos. O atalho não aciona dispositivos. Instalar voz
   ou salvar saída não significa que áudio audível foi confirmado.

## Progresso, falhas e cancelamento

As etapas rodam na fila local do backend, fora da thread Tk e sem esperar
inicialização do FCC. Uma única ação é admitida por vez. O painel mostra o
progresso por etapa, resultado e verificações básicas; não inventa porcentagens
de download. Parar permanece acessível enquanto os botões de ação ficam
desabilitados. A interface volta a permitir tentativa explícita após erro.

Parar compartilha o cancelamento já existente do backend. Interrompe instalação,
pull, preparação STT ou inferência conforme o adaptador; I/O de download pode
aguardar o timeout de rede vigente. Componentes já publicados e pesos já baixados
não são desfeitos. Uma tentativa posterior reutiliza componentes válidos ou o
cache disponível; não há promessa de retomada byte a byte de todo download.
O perfil não muda ao preparar componentes, iniciar servidor ou testar texto.

Saída de instalador/provedor e URLs com credenciais não são encaminhadas ao
painel. Falhas mostram categoria e orientação por etapa. Os relatórios básicos
mantêm separados presença/configuração, teste funcional e aceite físico.

## Ciclo de vida do servidor

O servidor iniciado pela GUI pertence à janela e é encerrado, com seu grupo de
processos, ao fechar Jarvis ou selecionar **Parar servidor desta janela**. Pesos
e instalação persistem. Um perfil Local já salvo tenta iniciar/reutilizar o
servidor ao reabrir a GUI, sem reinstalar ou baixar componentes. FCC não inicia
esse servidor automaticamente. O servidor gerenciado fica disponível também
para clientes locais enquanto a janela estiver aberta.

Se já existir servidor respondendo no endereço de loopback, a GUI o reutiliza
e informa que é externo. Não altera sua configuração nem o encerra. CPU,
paralelismo e ausência de nuvem precisam ser verificados nesse daemon separado;
as variáveis solicitadas ao processo próprio não provam isolamento de rede.

## Evidências e limites

Os testes usam loop de eventos Tk real com instalação controlada: erro seguido
de nova tentativa, responsividade, estado dos botões, Parar, foco/rolagem em
1040×640 com escala 1,8 e navegação para Voz. O backend também foi exercitado
com FCC bloqueado, cancelamento durante instalação e recusa de ação concorrente.
O teste de sessão Local cobre startup sem instaladores e limpeza ao fechar.

Um subprocesso HTTP controlado, com socket real e identidade/porta do próprio
PID, exercita prontidão e recolhimento do grupo. Não é daemon Ollama nem prova
inferência. Outros casos cobrem reutilização de servidor externo sem sinais,
cancelamento de startup, ambiente sem tokens/proxy, atualização do ponteiro do
motor e descarte da troca de perfil cancelada.

Na execução normal com adaptadores reais, o motor instalado foi reutilizado e
verificado. A consulta oficial do instalador Ollama falhou com `URLError`;
o resultado permaneceu falha e o perfil FCC foi preservado. Não houve microfone,
player ou inferência nesse ensaio. Relatório sanitizado em
[gui-setup-2026-11-06.json](metrics/gui-setup-2026-11-06.json).

Continuam pendentes os passos seguintes do plano: pesos/daemon Ollama real,
comparação e ferramenta Local com internet bloqueada, fala humana consentida,
detector Jarvis isolado, Kokoro real, jornada FCC real e 30 turnos físicos offline.
Este checkpoint não muda o perfil ou a voz padrão nem publica alterações locais
de equipes/multiagentes do usuário.

A consulta de prontidão usa `GET /api/version`, conforme o [contrato oficial
Ollama](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml), conferido
neste checkpoint. O fechamento normal aguarda a limpeza na thread local.
