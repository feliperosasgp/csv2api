from __future__ import annotations

import csv
import io

from lib.models import ExecutionResult, RowResult

_RESPONSE_BODY_MAX_CHARS = 500


def _truncate(text: str | None, max_chars: int = _RESPONSE_BODY_MAX_CHARS) -> str:
    if text is None:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncado]"
    return text


def to_csv_bytes(result: ExecutionResult) -> bytes:
    """
    Genera un CSV descargable con los resultados de la ejecución.

    Columnas: row_index, status_code, success, response_body (truncado), error, duration_ms
    Incluye una sección de summary al final.

    Returns:
        Bytes del CSV listo para st.download_button.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["row_index", "status_code", "success", "response_body", "error", "duration_ms"])

    for row in result.results:
        writer.writerow([
            row.row_index,
            row.status_code if row.status_code is not None else "",
            "true" if row.success else "false",
            _truncate(row.response_body),
            row.error or "",
            row.duration_ms,
        ])

    # Línea en blanco + summary
    writer.writerow([])
    writer.writerow(["--- SUMMARY ---"])
    writer.writerow(["total_rows", result.total_rows])
    writer.writerow(["successful", result.successful])
    writer.writerow(["failed", result.failed])

    if result.results:
        avg_ms = sum(r.duration_ms for r in result.results) / len(result.results)
        writer.writerow(["avg_duration_ms", round(avg_ms, 2)])

    return output.getvalue().encode("utf-8")


def build_summary(result: ExecutionResult) -> dict[str, str | int | float]:
    """Retorna un dict con las métricas resumen para mostrar en la UI."""
    avg_ms = 0.0
    if result.results:
        avg_ms = sum(r.duration_ms for r in result.results) / len(result.results)

    return {
        "total_rows": result.total_rows,
        "successful": result.successful,
        "failed": result.failed,
        "avg_duration_ms": round(avg_ms, 2),
        "success_rate": f"{(result.successful / result.total_rows * 100):.1f}%" if result.total_rows else "0%",
    }
