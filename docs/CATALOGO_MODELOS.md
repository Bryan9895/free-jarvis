# Modelos FCC: diagnóstico de catálogo

Análise de 23/10/2026: Free Claude Code oficial `Alishahryar1/free-claude-code`, main `fc86d53471bbf132e5f4021015a876b46499e21e`. Não houve acesso ao servidor localhost do usuário; versão e catálogo dessa instalação ainda precisam de comparação.

## Achados no código

- Jarvis consulta `/v1/models?view=responses`; `available_models()` retorna todos os registros com ID string. Não existe allowlist fixa de marcas ou modelos. A lista é requisitada novamente; não fica congelada no catálogo inicial do agente.
- FCC `api/routes.py` aceita visões claude, claude-desktop, messages e responses. A visão padrão usa aliases Claude; ela não comprova acesso a um Claude nativo nem modelos extras.
- FCC `application/model_catalog.py:read_model_catalog` une modelos configurados e metadados em cache. O GET não faz descoberta. A visão Responses atual projeta esse inventário completo, não testa inferência nem remove todos os modelos incompatíveis com ferramentas.
- O admin retorna provider_model_ref; Responses pode usar outro ID para o mesmo modelo (ex.: variante sem thinking). Comparar só strings gera falso modelo ausente.
- Refresh é uma ação separada no FCC (`POST /admin/api/models/refresh`), não executada pelo diagnóstico. Seus resultados podem indicar provedores que falharam. Configure/autentique o provedor na instalação do FCC e atualize o catálogo no painel local antes de culpar o cliente.
- Listar um modelo não comprova conta autorizada, cota ou endpoint acessível. O 404 NIM observado pelo usuário é falha de inferência upstream, não evidência de filtro no Jarvis.

## Como comparar no computador

Execute `jarvis-fcc --models-diagnostic`. O comando consulta somente GET: catálogo Responses, visão padrão e catálogo admin. Não chama modelos, não renova login e não atualiza provedores. Usa FCC_URL/FCC_TOKEN como o restante da CLI; saída inclui IDs e contagem por provedor, não credenciais. Admin pode estar indisponível em outra versão ou fora de loopback; isso é informado sem bloquear o restante.

Leia `admin.missing_in_responses`. Compare por provider_model_ref quando presente; sem esse campo, a comparação por ID é aproximada. Se estiver vazio, não há diferença entre os inventários comparados. Se um modelo falta em ambos, investigue o FCC/provedor e a versão local. Se has_more=true, o servidor exige tratamento adicional de paginação; o FCC oficial analisado retorna has_more=false.

Depois, liste por `jarvis-fcc --models` ou `/modelos` dentro do chat. Use `FCC_MODEL='ID_EXATO' jarvis-fcc --check-fcc` para teste separado de inferência (pode consumir cota). O diagnóstico de catálogo não precisa de microfone, GUI ou modelo padrão funcional.

## Fontes primárias

- https://github.com/Alishahryar1/free-claude-code/blob/fc86d53471bbf132e5f4021015a876b46499e21e/src/free_claude_code/api/model_catalog.py
- https://github.com/Alishahryar1/free-claude-code/blob/fc86d53471bbf132e5f4021015a876b46499e21e/src/free_claude_code/application/model_catalog.py
- https://github.com/Alishahryar1/free-claude-code/blob/fc86d53471bbf132e5f4021015a876b46499e21e/src/free_claude_code/api/admin_routes.py
