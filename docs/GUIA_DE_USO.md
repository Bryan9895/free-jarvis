# Uso, diagnóstico e recuperação

## Sessão e capacidades

Use `jarvis-fcc` para CLI, `jarvis-fcc --gui` para GUI ou `jarvis-fcc --voice` para gravação de seis segundos por Enter. A GUI mostra conversa, plano, histórico, métricas, modelo, perfis e capacidades. O modo manual apresenta uma pergunta por operação; o modo automático é padrão e aceita ações já permitidas, sem pedir `SIM` repetidamente. Fechar uma janela mantém uma confirmação pontual porque o aplicativo pode ter alterações não salvas. A revogação bloqueia novas ferramentas e cancela novas etapas; uma chamada já enviada ao FCC, navegador ou GNOME pode continuar até retornar. A CLI oferece `/permissoes status|auto|manual|revogar`, `/metricas`, `/plano`, `/retomar-plano` e `/resolver-etapa skip|retry`.

A GUI grava voz somente ao clicar em **Gravar**. A transcrição aparece no campo de texto e pode ser corrigida antes de **Enviar**. Falta de microfone ou de pacotes de voz não afeta o modo texto. Instale o conjunto opcional com `python -m pip install -e '.[voice]'`; ele inclui reconhecimento e Piper. Baixe uma voz com `python -m piper.download_voices --download-dir ~/.local/share/jarvis/voices pt_BR-faber-medium` e defina `JARVIS_PIPER_MODEL=~/.local/share/jarvis/voices/pt_BR-faber-medium.onnx`. A voz faber pt-BR usa modelo CC0. Não há palavra de ativação contínua.

As capacidades são verificadas novamente na execução, inclusive em chamadas diretas e no modo automático. O catálogo enviado ao modelo pode ser filtrado, mas não concede acesso. Acesso a outras pastas exige `JARVIS_ALLOWED_DIRS`; links simbólicos e caminhos resolvidos fora das raízes são recusados. GNOME Wayland também exige suporte das extensões e, para captura/entrada, autorização do portal. O navegador usa Chromium headless separado, sem cookies do Firefox pessoal; bloqueia protocolos e destinos locais/reservados. Resolução DNS pode mudar entre verificação e conexão, portanto não use o navegador isolado como fronteira absoluta contra redes privadas.

## Diagnóstico por camada

| Pergunta | Comando |
| --- | --- |
| Pacote e extras disponíveis | `jarvis-fcc --doctor` |
| Servidor FCC alcançável | `jarvis-fcc --health` |
| Modelos anunciados | `jarvis-fcc --models` |
| Modelo responde de fato | `jarvis-fcc --check-fcc` |
| GNOME/portais detectados | `jarvis-fcc --desktop-info` |
| Inventário de janelas | `jarvis-fcc --windows-diagnostic` |
| Testes automáticos | `python -m unittest discover -s tests -q` |

`--health` não comprova inferência, e inferência não comprova ferramenta GNOME. Se a janela desejada não aparecer, verifique as extensões GNOME compatíveis com sua versão; a instalação delas é manual. Se houver várias janelas semelhantes, especifique título ou escolha uma antes de agir. A GUI não deve ser executada sem sessão gráfica; a CLI segue disponível.

## Dados, atualização e falhas

O banco padrão é `~/.local/share/jarvis-fcc/memory.sqlite3`; `JARVIS_DB` altera o caminho. Antes de uma atualização importante, feche o programa e faça cópia do arquivo. A migração SQLite usa `PRAGMA user_version`, mantém tabelas e linhas antigas e cria as novas estruturas ao abrir. Para voltar à versão anterior, restaure a cópia do banco correspondente; não suponha que código antigo entenda o esquema novo.

Uma etapa interrompida ou com efeito incerto não é repetida automaticamente. Inspecione `/plano`, confirme o efeito no sistema e use `/resolver-etapa skip` se já aconteceu ou `/resolver-etapa retry` se é seguro repetir. Depois use `/retomar-plano`. Para falha de navegador, repita o diagnóstico de pacote/Chromium; timeouts encerram o subprocesso para evitar resposta atrasada. Para FCC indisponível, confira URL, token, modelo e servidor; o histórico local continua no banco.

## Validação física pendente

Em Ubuntu GNOME Wayland do usuário: verificar Firefox e VS Code lado a lado com janelas únicas, aplicativo com tamanho mínimo, janela com diálogo de salvamento, restauração parcial de perfil e cancelamento durante tarefa. O movimento real entre dois monitores exige dois monitores conectados. Registrar versão do GNOME, extensões, resoluções, comando, estado antes/depois e resultado; não marcar como validado somente pela suíte ou por simulação.
