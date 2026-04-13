from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from lib.models import EndpointConfig, MappingTemplate


class MappingError(Exception):
    pass


_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _extract_placeholders(template: str) -> list[str]:
    """Extrae todos los nombres de placeholder únicos de un string template."""
    return list(dict.fromkeys(_PLACEHOLDER_RE.findall(template)))


def _replace_placeholders(template: str, row: dict[str, Any]) -> str:
    """
    Reemplaza {column_name} con el valor de la fila correspondiente.

    - Valores NaN/None → "null" (para JSON válido).
    - Si un placeholder no existe en la fila → MappingError.
    """
    missing = [p for p in _extract_placeholders(template) if p not in row]
    if missing:
        raise MappingError(
            f"Placeholders no encontrados en el CSV: {', '.join(missing)}"
        )

    def replacer(match: re.Match) -> str:
        key = match.group(1)
        value = row[key]
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "null"
        return str(value)

    return _PLACEHOLDER_RE.sub(replacer, template)


def resolve_url(config: EndpointConfig, row: dict[str, Any]) -> str:
    """Resuelve placeholders en la URL del endpoint."""
    try:
        return _replace_placeholders(config.url, row)
    except MappingError as e:
        raise MappingError(f"Error en URL: {e}")


def resolve_headers(config: EndpointConfig, row: dict[str, Any]) -> dict[str, str]:
    """Resuelve placeholders en los headers del endpoint."""
    resolved: dict[str, str] = {}
    for key, value in config.headers.items():
        try:
            resolved[key] = _replace_placeholders(value, row)
        except MappingError as e:
            raise MappingError(f"Error en header '{key}': {e}")
    return resolved


def resolve_body(template: MappingTemplate, row: dict[str, Any]) -> dict[str, Any] | None:
    """
    Resuelve el body template para una fila.

    Returns:
        dict parseado del JSON resuelto, o None si el template está vacío.

    Raises:
        MappingError: Si el template tiene placeholders inválidos o el JSON resultante es inválido.
    """
    body_str = template.body_template.strip()
    if not body_str:
        return None

    try:
        resolved_str = _replace_placeholders(body_str, row)
    except MappingError as e:
        raise MappingError(f"Error en body template: {e}")

    try:
        return json.loads(resolved_str)
    except json.JSONDecodeError as e:
        raise MappingError(
            f"El body template no produce JSON válido después del reemplazo: {e}\n"
            f"Resultado: {resolved_str[:200]}"
        )


def resolve_row(
    config: EndpointConfig,
    template: MappingTemplate,
    row: pd.Series,
) -> tuple[str, dict[str, str], dict[str, Any] | None]:
    """
    Resuelve URL, headers y body para una fila del DataFrame.

    Returns:
        Tupla (url_resuelta, headers_resueltos, body_resuelto_o_None)
    """
    row_dict = row.to_dict()

    url = resolve_url(config, row_dict)
    headers = resolve_headers(config, row_dict)
    body = resolve_body(template, row_dict) if config.method not in ("GET", "DELETE") else None

    return url, headers, body


def validate_template(body_template: str, columns: list[str]) -> list[str]:
    """
    Valida que todos los placeholders del template existen en las columnas del CSV.

    Returns:
        Lista de placeholders que NO se encontraron en las columnas (vacía si todo OK).
    """
    placeholders = _extract_placeholders(body_template)
    return [p for p in placeholders if p not in columns]
