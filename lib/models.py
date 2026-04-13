from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class EndpointConfig(BaseModel):
    url: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    headers: dict[str, str] = {}
    timeout_seconds: int = 30
    rate_limit_ms: int = 100
    max_retries: int = 0

    @field_validator("url")
    @classmethod
    def url_must_be_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("URL no puede estar vacía")
        return v.strip()

    @field_validator("timeout_seconds")
    @classmethod
    def timeout_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("timeout_seconds debe ser mayor a 0")
        return v

    @field_validator("rate_limit_ms")
    @classmethod
    def rate_limit_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("rate_limit_ms no puede ser negativo")
        return v

    @field_validator("max_retries")
    @classmethod
    def max_retries_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_retries no puede ser negativo")
        return v


class MappingTemplate(BaseModel):
    body_template: str = ""
    column_mapping: dict[str, str] = {}


class RowResult(BaseModel):
    row_index: int
    status_code: int | None = None
    response_body: str | None = None
    error: str | None = None
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.error is None and self.status_code is not None and self.status_code < 400


class ExecutionResult(BaseModel):
    total_rows: int
    successful: int
    failed: int
    results: list[RowResult]

    @model_validator(mode="after")
    def validate_counts(self) -> "ExecutionResult":
        if self.successful + self.failed > self.total_rows:
            raise ValueError("successful + failed no puede superar total_rows")
        return self
