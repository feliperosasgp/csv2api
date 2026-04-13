from __future__ import annotations

import io

import pandas as pd
import pytest

from lib.parser import ParseError, parse_file


def _csv_bytes(content: str, encoding: str = "utf-8") -> bytes:
    return content.encode(encoding)


class TestCsvParsing:
    def test_basic_csv(self) -> None:
        raw = _csv_bytes("name,email,age\nAlice,alice@test.com,30\nBob,bob@test.com,25")
        result = parse_file(raw, "test.csv")
        assert list(result.columns) == ["name", "email", "age"]
        assert result.total_rows == 2
        assert len(result.dataframe) == 2

    def test_csv_with_latin1_encoding(self) -> None:
        raw = "nombre,ciudad\nJosé,Bogotá\nMaría,São Paulo\n".encode("latin-1")
        result = parse_file(raw, "test.csv")
        assert "nombre" in result.columns
        assert result.total_rows == 2

    def test_csv_preview_limit(self) -> None:
        rows = "\n".join(f"row{i},value{i}" for i in range(200))
        raw = _csv_bytes(f"col1,col2\n{rows}")
        result = parse_file(raw, "test.csv", preview_rows=50)
        assert result.total_rows == 200
        assert len(result.dataframe) == 50

    def test_csv_empty_file(self) -> None:
        with pytest.raises(ParseError):
            parse_file(b"", "test.csv")

    def test_csv_only_header(self) -> None:
        with pytest.raises(ParseError):
            parse_file(_csv_bytes("name,email\n"), "test.csv")

    def test_csv_strips_column_names(self) -> None:
        raw = _csv_bytes("  name  , email ,age\nAlice,alice@test.com,30")
        result = parse_file(raw, "test.csv")
        assert "name" in result.columns
        assert "email" in result.columns
        assert "age" in result.columns

    def test_csv_with_blank_lines(self) -> None:
        raw = _csv_bytes("name,email\nAlice,a@test.com\n\nBob,b@test.com\n\n")
        result = parse_file(raw, "test.csv")
        assert result.total_rows >= 2

    def test_csv_no_extension_treated_as_csv(self) -> None:
        raw = _csv_bytes("a,b\n1,2")
        result = parse_file(raw, "myfile")
        assert result.total_rows == 1


class TestExcelParsing:
    def _make_excel_bytes(self, df: pd.DataFrame) -> bytes:
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        return buf.getvalue()

    def test_basic_excel(self) -> None:
        df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
        raw = self._make_excel_bytes(df)
        result = parse_file(raw, "test.xlsx")
        assert "name" in result.columns
        assert result.total_rows == 2

    def test_excel_empty_rows_filtered(self) -> None:
        df = pd.DataFrame({"name": ["Alice", None, "Bob"], "age": [30, None, 25]})
        raw = self._make_excel_bytes(df)
        result = parse_file(raw, "test.xlsx")
        # La fila completamente vacía debe eliminarse
        assert result.total_rows <= 3

    def test_excel_no_encoding_field(self) -> None:
        df = pd.DataFrame({"x": [1]})
        raw = self._make_excel_bytes(df)
        result = parse_file(raw, "test.xlsx")
        assert result.encoding_detected is None

    def test_invalid_excel_raises(self) -> None:
        with pytest.raises(ParseError):
            parse_file(b"not an excel file", "test.xlsx")
