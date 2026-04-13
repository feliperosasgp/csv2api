from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import httpx
import pandas as pd

from lib.mapper import MappingError, resolve_row
from lib.models import EndpointConfig, ExecutionResult, MappingTemplate, RowResult


ProgressCallback = Callable[[int, int, RowResult], None]


async def _execute_single(
    client: httpx.AsyncClient,
    config: EndpointConfig,
    template: MappingTemplate,
    row: pd.Series,
    row_index: int,
) -> RowResult:
    """Ejecuta una sola fila contra el endpoint. Nunca levanta excepción."""
    start = time.perf_counter()

    try:
        url, headers, body = resolve_row(config, template, row)
    except MappingError as e:
        return RowResult(
            row_index=row_index,
            error=str(e),
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )

    last_error: str | None = None
    last_status: int | None = None
    last_body: str | None = None

    attempts = config.max_retries + 1
    for attempt in range(attempts):
        if attempt > 0:
            backoff = 0.5 * (2 ** (attempt - 1))
            await asyncio.sleep(backoff)

        try:
            response = await client.request(
                method=config.method,
                url=url,
                headers=headers,
                json=body,
                timeout=config.timeout_seconds,
            )
            last_status = response.status_code
            last_body = response.text
            last_error = None
            break  # éxito — no reintentar
        except httpx.TimeoutException:
            last_error = f"Timeout después de {config.timeout_seconds}s"
        except httpx.RequestError as e:
            last_error = f"Error de red: {e}"
        except Exception as e:
            last_error = f"Error inesperado: {e}"

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    return RowResult(
        row_index=row_index,
        status_code=last_status,
        response_body=last_body,
        error=last_error,
        duration_ms=duration_ms,
    )


async def execute_all(
    df: pd.DataFrame,
    config: EndpointConfig,
    template: MappingTemplate,
    progress_callback: ProgressCallback | None = None,
    stop_flag: list[bool] | None = None,
    max_concurrent: int = 1,
) -> ExecutionResult:
    """
    Ejecuta todos los requests del DataFrame.

    Args:
        df: DataFrame completo con todas las filas a procesar.
        config: Configuración del endpoint.
        template: Template de mapeo del body.
        progress_callback: Llamada con (current, total, row_result) tras cada request.
        stop_flag: Lista mutable de un elemento; si stop_flag[0] es True, cancela la ejecución.
        max_concurrent: Número máximo de requests concurrentes (1 = secuencial).

    Returns:
        ExecutionResult con todos los resultados.
    """
    total = len(df)
    results: list[RowResult] = []
    semaphore = asyncio.Semaphore(max(1, min(max_concurrent, 5)))

    async with httpx.AsyncClient() as client:
        if max_concurrent <= 1:
            # Modo secuencial — más predecible, rate limiting explícito
            for i, (_, row) in enumerate(df.iterrows()):
                if stop_flag and stop_flag[0]:
                    break

                result = await _execute_single(client, config, template, row, i)
                results.append(result)

                if progress_callback:
                    progress_callback(i + 1, total, result)

                if config.rate_limit_ms > 0 and i < total - 1:
                    await asyncio.sleep(config.rate_limit_ms / 1000)
        else:
            # Modo concurrente con semaphore
            async def run_with_semaphore(i: int, row: pd.Series) -> RowResult:
                async with semaphore:
                    result = await _execute_single(client, config, template, row, i)
                    if progress_callback:
                        progress_callback(len(results) + 1, total, result)
                    return result

            rows = list(df.iterrows())
            tasks = [
                asyncio.create_task(run_with_semaphore(i, row))
                for i, (_, row) in enumerate(rows)
            ]

            for task in asyncio.as_completed(tasks):
                if stop_flag and stop_flag[0]:
                    for t in tasks:
                        t.cancel()
                    break
                result = await task
                results.append(result)

    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    return ExecutionResult(
        total_rows=total,
        successful=successful,
        failed=failed,
        results=results,
    )


def run_execution(
    df: pd.DataFrame,
    config: EndpointConfig,
    template: MappingTemplate,
    progress_callback: ProgressCallback | None = None,
    stop_flag: list[bool] | None = None,
    max_concurrent: int = 1,
) -> ExecutionResult:
    """
    Bridge sync → async para llamar desde Streamlit.
    Usa asyncio.run() para ejecutar el motor async.
    """
    return asyncio.run(
        execute_all(
            df=df,
            config=config,
            template=template,
            progress_callback=progress_callback,
            stop_flag=stop_flag,
            max_concurrent=max_concurrent,
        )
    )
