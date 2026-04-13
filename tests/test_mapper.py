from __future__ import annotations

import json

import pandas as pd
import pytest

from lib.mapper import MappingError, resolve_body, resolve_headers, resolve_url, validate_template
from lib.models import EndpointConfig, MappingTemplate


def _config(url: str = "https://api.test.com", method: str = "POST", headers: dict | None = None) -> EndpointConfig:
    return EndpointConfig(url=url, method=method, headers=headers or {})


def _template(body: str = "") -> MappingTemplate:
    return MappingTemplate(body_template=body)


def _row(**kwargs) -> dict:
    return kwargs


class TestResolveUrl:
    def test_static_url(self) -> None:
        cfg = _config(url="https://api.test.com/endpoint")
        result = resolve_url(cfg, _row())
        assert result == "https://api.test.com/endpoint"

    def test_url_with_placeholder(self) -> None:
        cfg = _config(url="https://api.test.com/contacts/{id}")
        result = resolve_url(cfg, _row(id="12345"))
        assert result == "https://api.test.com/contacts/12345"

    def test_url_multiple_placeholders(self) -> None:
        cfg = _config(url="https://api.test.com/{org}/users/{user_id}")
        result = resolve_url(cfg, _row(org="acme", user_id="99"))
        assert result == "https://api.test.com/acme/users/99"

    def test_url_missing_placeholder_raises(self) -> None:
        cfg = _config(url="https://api.test.com/users/{missing_col}")
        with pytest.raises(MappingError):
            resolve_url(cfg, _row())


class TestResolveHeaders:
    def test_static_headers(self) -> None:
        cfg = _config(headers={"Content-Type": "application/json"})
        result = resolve_headers(cfg, _row())
        assert result == {"Content-Type": "application/json"}

    def test_header_with_placeholder(self) -> None:
        cfg = _config(headers={"Authorization": "Bearer {token}"})
        result = resolve_headers(cfg, _row(token="abc123"))
        assert result["Authorization"] == "Bearer abc123"

    def test_missing_placeholder_in_header_raises(self) -> None:
        cfg = _config(headers={"X-Key": "{missing}"})
        with pytest.raises(MappingError):
            resolve_headers(cfg, _row())


class TestResolveBody:
    def test_simple_body(self) -> None:
        tmpl = _template('{"name": "{nombre}", "email": "{correo}"}')
        result = resolve_body(tmpl, _row(nombre="Alice", correo="alice@test.com"))
        assert result == {"name": "Alice", "email": "alice@test.com"}

    def test_nested_json_body(self) -> None:
        tmpl = _template('{"user": {"name": "{nombre}", "contact": {"email": "{correo}"}}}')
        result = resolve_body(tmpl, _row(nombre="Bob", correo="bob@test.com"))
        assert result == {"user": {"name": "Bob", "contact": {"email": "bob@test.com"}}}

    def test_null_value_for_nan(self) -> None:
        import math
        tmpl = _template('{"value": "{campo}"}')
        result = resolve_body(tmpl, {"campo": float("nan")})
        assert result == {"value": "null"}  # el JSON resuelto tiene "null" como string
        # Pero al hacer json.loads, "null" como valor de string no es None —
        # validamos que no crashea y que el placeholder se reemplazó
        tmpl2 = _template('{"value": {campo}}')
        result2 = resolve_body(tmpl2, {"campo": float("nan")})
        assert result2 == {"value": None}

    def test_empty_template_returns_none(self) -> None:
        tmpl = _template("")
        assert resolve_body(tmpl, _row()) is None

    def test_missing_column_raises(self) -> None:
        tmpl = _template('{"id": "{nonexistent}"}')
        with pytest.raises(MappingError):
            resolve_body(tmpl, _row(otro="valor"))

    def test_invalid_json_template_raises(self) -> None:
        tmpl = _template('{"name": "{nombre}" INVALID}')
        with pytest.raises(MappingError):
            resolve_body(tmpl, _row(nombre="Alice"))

    def test_numeric_placeholder(self) -> None:
        tmpl = _template('{"age": {age}, "name": "{name}"}')
        result = resolve_body(tmpl, _row(age=30, name="Alice"))
        assert result == {"age": 30, "name": "Alice"}


class TestValidateTemplate:
    def test_all_placeholders_exist(self) -> None:
        missing = validate_template('{"a": "{col1}", "b": "{col2}"}', ["col1", "col2", "col3"])
        assert missing == []

    def test_missing_placeholder_reported(self) -> None:
        missing = validate_template('{"a": "{col1}", "b": "{missing}"}', ["col1"])
        assert "missing" in missing

    def test_no_placeholders(self) -> None:
        missing = validate_template('{"static": "value"}', ["col1"])
        assert missing == []
