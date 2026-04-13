from __future__ import annotations

import io
from typing import NamedTuple

import chardet
import pandas as pd


class ParseResult(NamedTuple):
    dataframe: pd.DataFrame
    columns: list[str]
    total_rows: int
    encoding_detected: str | None


class ParseError(Exception):
    pass


def _detect_encoding(raw: bytes) -> str:
    result = chardet.detect(raw)
    encoding = result.get("encoding") or "utf-8"
    # chardet a veces devuelve ascii para utf-8 puro — utf-8 es siempre compatible
    if encoding.lower() == "ascii":
        encoding = "utf-8"
    return encoding


def parse_file(
    file_content: bytes,
    filename: str,
    preview_rows: int = 100,
) -> ParseResult:
    """
    Parsea un archivo CSV o Excel y retorna un ParseResult.

    Args:
        file_content: Contenido del archivo en bytes.
        filename: Nombre del archivo (se usa para detectar extensión).
        preview_rows: Máximo de filas a retornar en el DataFrame.

    Returns:
        ParseResult con el DataFrame (hasta preview_rows filas), lista de columnas,
        total de filas en el archivo, y encoding detectado.

    Raises:
        ParseError: Si el archivo no se puede parsear o está vacío.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in ("xlsx", "xls"):
        return _parse_excel(file_content, preview_rows)
    elif ext == "csv":
        return _parse_csv(file_content, preview_rows)
    else:
        # Intentar como CSV por defecto
        return _parse_csv(file_content, preview_rows)


def _parse_csv(raw: bytes, preview_rows: int) -> ParseResult:
    encoding = _detect_encoding(raw)

    try:
        text = raw.decode(encoding, errors="replace")
    except Exception:
        text = raw.decode("utf-8", errors="replace")

    try:
        # Leer todo para contar filas reales
        df_full = pd.read_csv(
            io.StringIO(text),
            skip_blank_lines=True,
            on_bad_lines="skip",
        )
    except pd.errors.EmptyDataError:
        raise ParseError("El archivo CSV está vacío o no tiene datos.")
    except Exception as e:
        raise ParseError(f"Error al parsear CSV: {e}")

    if df_full.empty:
        raise ParseError("El archivo CSV no contiene filas de datos.")

    # Limpiar nombres de columnas
    df_full.columns = [str(c).strip() for c in df_full.columns]

    total_rows = len(df_full)
    df_preview = df_full.head(preview_rows)

    return ParseResult(
        dataframe=df_preview,
        columns=list(df_preview.columns),
        total_rows=total_rows,
        encoding_detected=encoding,
    )


def _parse_excel(raw: bytes, preview_rows: int) -> ParseResult:
    try:
        df_full = pd.read_excel(
            io.BytesIO(raw),
            sheet_name=0,
        )
    except Exception as e:
        raise ParseError(f"Error al parsear Excel: {e}")

    if df_full.empty:
        raise ParseError("El archivo Excel no contiene filas de datos.")

    # Eliminar filas completamente vacías
    df_full = df_full.dropna(how="all")

    if df_full.empty:
        raise ParseError("El archivo Excel solo contiene filas vacías.")

    # Limpiar nombres de columnas
    df_full.columns = [str(c).strip() for c in df_full.columns]

    total_rows = len(df_full)
    df_preview = df_full.head(preview_rows)

    return ParseResult(
        dataframe=df_preview,
        columns=list(df_preview.columns),
        total_rows=total_rows,
        encoding_detected=None,
    )


def parse_file_full(
    file_content: bytes,
    filename: str,
) -> ParseResult:
    """
    Igual que parse_file pero retorna TODAS las filas (sin límite de preview).
    Usar al momento de ejecutar, no para mostrar en UI.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in ("xlsx", "xls"):
        return _parse_excel(file_content, preview_rows=10_000_000)
    else:
        return _parse_csv(file_content, preview_rows=10_000_000)
