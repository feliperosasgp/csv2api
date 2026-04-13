from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pandas as pd
import pytest

from lib.executor import execute_all, run_execution
from lib.models import EndpointConfig, MappingTemplate


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _config(**kwargs) -> EndpointConfig:
    defaults = dict(
        url="https://api.test.com/endpoint",
        method="POST",
        headers={},
        timeout_seconds=5,
        rate_limit_ms=0,
        max_retries=0,
    )
    defaults.update(kwargs)
    return EndpointConfig(**defaults)


def _template(body: str = '{"id": "{id}"}') -> MappingTemplate:
    return MappingTemplate(body_template=body)


def _mock_response(status_code: int = 200, text: str = '{"ok": true}') -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestExecuteAll:
    @pytest.mark.asyncio
    async def test_successful_requests(self) -> None:
        df = _df([{"id": "1"}, {"id": "2"}, {"id": "3"}])

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200)
            result = await execute_all(df, _config(), _template())

        assert result.total_rows == 3
        assert result.successful == 3
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_failed_request_continues(self) -> None:
        df = _df([{"id": "1"}, {"id": "2"}])
        responses = [_mock_response(500, "error"), _mock_response(200, "ok")]

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = responses
            result = await execute_all(df, _config(), _template())

        assert result.total_rows == 2
        # La fila con 500 se cuenta como fallida
        assert result.failed == 1
        assert result.successful == 1

    @pytest.mark.asyncio
    async def test_network_error_captured(self) -> None:
        df = _df([{"id": "1"}])

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.RequestError("connection refused")
            result = await execute_all(df, _config(), _template())

        assert result.total_rows == 1
        assert result.failed == 1
        assert result.results[0].error is not None
        assert "connection refused" in result.results[0].error or "red" in result.results[0].error

    @pytest.mark.asyncio
    async def test_timeout_error_captured(self) -> None:
        df = _df([{"id": "1"}])

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.TimeoutException("timed out")
            result = await execute_all(df, _config(), _template())

        assert result.results[0].error is not None
        assert "Timeout" in result.results[0].error

    @pytest.mark.asyncio
    async def test_stop_flag_cancels_execution(self) -> None:
        df = _df([{"id": str(i)} for i in range(10)])
        stop_flag = [False]
        call_count = 0

        async def slow_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                stop_flag[0] = True
            await asyncio.sleep(0)
            return _mock_response(200)

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = slow_request
            result = await execute_all(df, _config(), _template(), stop_flag=stop_flag)

        assert len(result.results) < 10

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self) -> None:
        df = _df([{"id": "1"}])
        call_count = 0

        async def flaky_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.RequestError("temporary error")
            return _mock_response(200)

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = flaky_request
            result = await execute_all(df, _config(max_retries=3), _template())

        assert result.successful == 1
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_missing_placeholder_in_row_counted_as_failed(self) -> None:
        df = _df([{"other_col": "1"}])
        template = _template('{"id": "{id}"}')  # "id" no existe en el df

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock):
            result = await execute_all(df, _config(), template)

        assert result.failed == 1
        assert result.results[0].error is not None

    @pytest.mark.asyncio
    async def test_progress_callback_called(self) -> None:
        df = _df([{"id": "1"}, {"id": "2"}])
        calls: list[tuple] = []

        def callback(current: int, total: int, row_result) -> None:
            calls.append((current, total))

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(200)
            await execute_all(df, _config(), _template(), progress_callback=callback)

        assert len(calls) == 2
        assert calls[0] == (1, 2)
        assert calls[1] == (2, 2)


class TestRunExecution:
    def test_sync_bridge_works(self) -> None:
        df = _df([{"id": "42"}])

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _mock_response(201)
            result = run_execution(df, _config(), _template())

        assert result.successful == 1
        assert result.results[0].status_code == 201
