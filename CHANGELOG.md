# Histórico de alterações

## Em desenvolvimento — v0.7.0

- Registro central do catálogo com esquema, capacidade e executor de cada ferramenta; extensões Python exigem registro explícito.
- Filtragem das ferramentas anunciadas e bloqueio no limite de execução por `JARVIS_ENABLED_CAPABILITIES`, inclusive no modo `--auto-approve`.
- Entrada gráfica experimental permanece sujeita ao opt-in `JARVIS_ENABLE_DESKTOP_INPUT=1`; testes automatizados de registro, negação e extensibilidade.
- Medições por chamada de ferramenta, com estado e duração, em trilha limitada a 100 registros sem argumentos; expostas em `/metricas`.

## Em desenvolvimento — v0.6.0

- Ferramenta `desktop_spaces` para consultar monitores, áreas úteis e áreas de trabalho GNOME com resposta D-Bus validada; roteamento direto de pedidos informativos.
- Consulta confirmada no Ubuntu GNOME Wayland real com um monitor e duas áreas de trabalho.
- Alternância de área e movimento de janela por número humano (a partir de 1), com revalidação, verificação do compositor e histórico sanitizado; fluxo de ida e volta confirmado no GNOME real com XTerm descartável.
- Movimento de uma janela entre monitores por número ou destino único, com topologia revalidada e confirmação do monitor final. Teste físico de destino inexistente/atual passou com monitor único; movimento físico com dois monitores segue pendente.
- Perfis completos de ambiente em SQLite: captura de aplicativos, monitor, área, geometria e área ativa; restauração por etapas com abertura XDG opcional, verificação final e bloqueio de abertura incerta repetida. Testes reais com XTerm e GNOME Calculator passaram; multimonitor físico pendente.

## Em desenvolvimento — v0.5.0

- Posicionamento de janelas por porcentagem ou pixels da área útil, grades de três/quatro janelas e perfis SQLite reutilizáveis.
- Consulta de foco, fechamento controlado e histórico sanitizado de ações de janela.
- Validação física controlada no GNOME Wayland com XTerm descartável: centro, pixels, foco, fechamento, grades, ambiguidade e restauração de perfil.
- Correção do parser `GetFocused` para o campo `uint64` exibido por `gdbus` e aplicação de `Move` após `MoveResize` quando o compositor não desloca a janela no mesmo comando.

Limites conhecidos: tamanho mínimo imposto pelo aplicativo pode deixar a geometria não verificada; faltam testes com monitor adicional e diálogos de salvamento.
