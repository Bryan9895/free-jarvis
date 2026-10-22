# Histórico de alterações

## Em desenvolvimento — v0.5.0

- Posicionamento de janelas por porcentagem ou pixels da área útil, grades de três/quatro janelas e perfis SQLite reutilizáveis.
- Consulta de foco, fechamento controlado e histórico sanitizado de ações de janela.
- Validação física controlada no GNOME Wayland com XTerm descartável: centro, pixels, foco, fechamento, grades, ambiguidade e restauração de perfil.
- Correção do parser `GetFocused` para o campo `uint64` exibido por `gdbus` e aplicação de `Move` após `MoveResize` quando o compositor não desloca a janela no mesmo comando.

Limites conhecidos: tamanho mínimo imposto pelo aplicativo pode deixar a geometria não verificada; faltam testes com monitor adicional e diálogos de salvamento.
