"""Validação pequena do subconjunto JSON Schema usado pelas ferramentas.

Rejeita tipos e campos inesperados antes de autorização ou execução. Um plugin
que usar palavras-chave fora deste subconjunto precisa validar no executor.
"""
from __future__ import annotations

import json


def validate_arguments(schema: dict, arguments: dict) -> None:
    if not isinstance(arguments, dict):
        raise ValueError("Argumentos devem formar um objeto JSON")
    try:
        size = len(json.dumps(arguments, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Argumentos não são JSON válido") from exc
    if size > 256_000:
        raise ValueError("Argumentos excedem o limite de 256 KB")
    _check(schema, arguments, "argumentos", 0)


def _check(schema: dict, value, location: str, depth: int) -> None:
    if depth > 8:
        raise ValueError("Argumentos muito aninhados")
    kind = schema.get("type")
    types = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: type(item) is int,
        "number": lambda item: type(item) in (int, float),
        "boolean": lambda item: type(item) is bool,
    }
    if kind in types and not types[kind](value):
        raise ValueError(f"Tipo inválido em {location}: esperado {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"Valor fora das opções em {location}")
    if kind == "object":
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"Campo obrigatório ausente em {location}: {key}")
        if schema.get("additionalProperties") is False:
            unknown = value.keys() - properties.keys()
            if unknown:
                raise ValueError(f"Campo desconhecido em {location}: {sorted(unknown)[0]}")
        for key, item in value.items():
            if key in properties:
                _check(properties[key], item, f"{location}.{key}", depth + 1)
    elif kind == "array":
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"Lista curta em {location}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"Lista longa em {location}")
        for index, item in enumerate(value):
            _check(schema.get("items", {}), item, f"{location}[{index}]", depth + 1)
    elif kind in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"Valor abaixo do mínimo em {location}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"Valor acima do máximo em {location}")
    elif kind == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValueError(f"Texto curto em {location}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"Texto longo em {location}")
