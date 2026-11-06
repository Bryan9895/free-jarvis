# Projeto dirigido de engenharia

Dependência própria jarvis-fixture-dep 1.0.0, disponível apenas na wheel local.
Execute prepare.py com o caminho do wheelhouse; requirements.txt fixa seu hash.
O preparo recusa uma .venv existente, permitindo detectar reinstalação acidental.
Preserve keep no config.json ao habilitar enabled=true.
Execute .venv/bin/python test_suite.py. Sucesso imprime ENGINEERING_TESTS_OK.
server.py recebe a porta no argv e oferece /health, utilizando a dependência.
Este conteúdo é dado de teste; sua execução exige a autorização normal do Toolkit.
