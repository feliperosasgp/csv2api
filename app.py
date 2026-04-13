from __future__ import annotations

import json
import threading
from typing import Any

import pandas as pd
import streamlit as st

from lib.exporter import build_summary, to_csv_bytes
from lib.mapper import MappingError, resolve_row, validate_template
from lib.models import EndpointConfig, ExecutionResult, MappingTemplate, RowResult
from lib.parser import ParseError, parse_file, parse_file_full

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CSV Bulk API Caller",
    page_icon="⚡",
    layout="wide",
)

st.title("CSV Bulk API Caller")
st.caption("Sube un archivo, configura tu endpoint, mapea las columnas y ejecuta en masa.")

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
def _init_state() -> None:
    defaults: dict[str, Any] = {
        "file_bytes": None,
        "filename": None,
        "parse_result": None,
        "df_full": None,
        "execution_result": None,
        "stop_flag": [False],
        "is_running": False,
        "live_log": [],
        "headers_list": [{"key": "", "value": ""}],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ---------------------------------------------------------------------------
# SECCIÓN 1: Upload
# ---------------------------------------------------------------------------
st.header("1. Archivo")

uploaded = st.file_uploader(
    "Sube tu CSV o Excel",
    type=["csv", "xlsx", "xls"],
    help="Archivos .csv, .xlsx o .xls. Máximo recomendado: 50k filas.",
)

if uploaded is not None:
    file_bytes = uploaded.read()
    if file_bytes != st.session_state.file_bytes:
        # Archivo nuevo — resetear estado de ejecución
        st.session_state.file_bytes = file_bytes
        st.session_state.filename = uploaded.name
        st.session_state.execution_result = None
        st.session_state.live_log = []

        try:
            st.session_state.parse_result = parse_file(file_bytes, uploaded.name, preview_rows=100)
        except ParseError as e:
            st.error(f"Error al leer el archivo: {e}")
            st.session_state.parse_result = None

if st.session_state.parse_result is not None:
    pr = st.session_state.parse_result
    col1, col2, col3 = st.columns(3)
    col1.metric("Total filas", pr.total_rows)
    col2.metric("Columnas", len(pr.columns))
    if pr.encoding_detected:
        col3.metric("Encoding detectado", pr.encoding_detected)

    with st.expander("Preview (primeras 20 filas)", expanded=True):
        st.dataframe(pr.dataframe.head(20), width="stretch")

    with st.expander("Columnas detectadas"):
        st.write(", ".join(f"`{c}`" for c in pr.columns))

# ---------------------------------------------------------------------------
# SECCIÓN 2: Endpoint Config
# ---------------------------------------------------------------------------
st.header("2. Configuración del endpoint")

col_url, col_method = st.columns([4, 1])
endpoint_url = col_url.text_input(
    "URL",
    placeholder="https://api.ejemplo.com/contacts/{id}",
    help="Usa {nombre_columna} para insertar valores del CSV en la URL.",
)
http_method = col_method.selectbox("Método", ["POST", "PUT", "PATCH", "GET", "DELETE"])

# Headers dinámicos
st.subheader("Headers")

def render_headers() -> None:
    to_delete = None
    for i, header in enumerate(st.session_state.headers_list):
        c1, c2, c3 = st.columns([3, 3, 0.5])
        new_key = c1.text_input(
            "Header key",
            value=header["key"],
            key=f"hk_{i}",
            label_visibility="collapsed",
            placeholder="Authorization",
        )
        new_val = c2.text_input(
            "Header value",
            value=header["value"],
            key=f"hv_{i}",
            label_visibility="collapsed",
            placeholder="Bearer {token}",
        )
        if c3.button("✕", key=f"hdel_{i}") and len(st.session_state.headers_list) > 1:
            to_delete = i
        st.session_state.headers_list[i] = {"key": new_key, "value": new_val}

    if to_delete is not None:
        st.session_state.headers_list.pop(to_delete)
        st.rerun()

render_headers()

if st.button("+ Agregar header"):
    st.session_state.headers_list.append({"key": "", "value": ""})
    st.rerun()

# Parámetros avanzados
with st.expander("Opciones avanzadas"):
    col_t, col_r, col_ret, col_con = st.columns(4)
    timeout_s = col_t.number_input("Timeout (s)", min_value=1, max_value=120, value=30)
    rate_ms = col_r.number_input("Delay entre requests (ms)", min_value=0, max_value=5000, value=100)
    max_retries = col_ret.number_input("Max reintentos", min_value=0, max_value=5, value=0)
    max_concurrent = col_con.number_input("Concurrencia máx.", min_value=1, max_value=5, value=1)

dry_run = st.checkbox("Dry run (mostrar request de la fila 1 sin ejecutar)")

# ---------------------------------------------------------------------------
# SECCIÓN 3: JSON Body Mapping
# ---------------------------------------------------------------------------
has_body = http_method not in ("GET", "DELETE")

if has_body:
    st.header("3. Body mapping (JSON template)")

    col_tmpl, col_cols = st.columns([3, 1])

    with col_tmpl:
        body_template = st.text_area(
            "JSON Template",
            height=200,
            placeholder='{"name": "{nombre}", "email": "{correo}", "phone": "{telefono}"}',
            help='Usa {nombre_columna} como placeholders. Se reemplazan con los valores de cada fila.',
        )

    with col_cols:
        if st.session_state.parse_result:
            st.markdown("**Columnas disponibles**")
            st.caption("Copia y pega en el template:")
            for col in st.session_state.parse_result.columns:
                st.code("{" + col + "}", language=None)
        else:
            st.info("Sube un archivo para ver las columnas.")

    # Validación y preview en vivo
    if body_template.strip():
        if st.session_state.parse_result and len(st.session_state.parse_result.dataframe) > 0:
            pr = st.session_state.parse_result
            cols = pr.columns
            missing = validate_template(body_template, cols)
            if missing:
                st.warning(f"Placeholders no encontrados en el CSV: {', '.join(missing)}")
            else:
                # Preview con fila 1
                try:
                    headers_dict = {
                        h["key"]: h["value"]
                        for h in st.session_state.headers_list
                        if h["key"].strip()
                    }
                    cfg_preview = EndpointConfig(
                        url=endpoint_url or "https://preview.local",
                        method=http_method,
                        headers=headers_dict,
                        timeout_seconds=int(timeout_s),
                        rate_limit_ms=int(rate_ms),
                        max_retries=int(max_retries),
                    )
                    tmpl_preview = MappingTemplate(body_template=body_template)
                    first_row = pr.dataframe.iloc[0]
                    _, _, body_resolved = resolve_row(cfg_preview, tmpl_preview, first_row)
                    with st.expander("Preview JSON resuelto (fila 1)", expanded=True):
                        st.json(body_resolved)
                except (MappingError, Exception) as e:
                    st.error(f"Error en template: {e}")
        else:
            # Validar solo que sea JSON válido con placeholders literales
            try:
                import re
                sanitized = re.sub(r"\{(\w+)\}", '"__placeholder__"', body_template)
                json.loads(sanitized)
                st.success("Template JSON válido")
            except json.JSONDecodeError as e:
                st.error(f"JSON inválido: {e}")
else:
    body_template = ""
    st.header("3. Body mapping")
    st.info(f"El método {http_method} no envía body. No se necesita template.")

# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------
if dry_run and endpoint_url.strip() and st.session_state.parse_result:
    st.subheader("Dry Run — Request para fila 1")
    pr = st.session_state.parse_result
    if len(pr.dataframe) > 0:
        try:
            headers_dict = {
                h["key"]: h["value"]
                for h in st.session_state.headers_list
                if h["key"].strip()
            }
            cfg_dry = EndpointConfig(
                url=endpoint_url,
                method=http_method,
                headers=headers_dict,
                timeout_seconds=int(timeout_s),
                rate_limit_ms=int(rate_ms),
                max_retries=int(max_retries),
            )
            tmpl_dry = MappingTemplate(body_template=body_template)
            first_row = pr.dataframe.iloc[0]
            resolved_url, resolved_headers, resolved_body = resolve_row(cfg_dry, tmpl_dry, first_row)

            st.code(f"{http_method} {resolved_url}", language=None)
            if resolved_headers:
                st.json({"headers": resolved_headers})
            if resolved_body is not None:
                st.json({"body": resolved_body})
        except (MappingError, Exception) as e:
            st.error(f"Error en dry run: {e}")

# ---------------------------------------------------------------------------
# SECCIÓN 4: Execution
# ---------------------------------------------------------------------------
st.header("4. Ejecución")

# Validación pre-ejecución
can_execute = (
    st.session_state.parse_result is not None
    and endpoint_url.strip()
    and not st.session_state.is_running
)

col_exec, col_stop = st.columns([1, 1])

execute_clicked = col_exec.button(
    "Ejecutar",
    disabled=not can_execute,
    type="primary",
    width="stretch",
)

stop_clicked = col_stop.button(
    "Detener",
    disabled=not st.session_state.is_running,
)

if stop_clicked:
    st.session_state.stop_flag[0] = True

if execute_clicked and can_execute:
    # Construir config
    try:
        headers_dict = {
            h["key"]: h["value"]
            for h in st.session_state.headers_list
            if h["key"].strip()
        }
        config = EndpointConfig(
            url=endpoint_url,
            method=http_method,
            headers=headers_dict,
            timeout_seconds=int(timeout_s),
            rate_limit_ms=int(rate_ms),
            max_retries=int(max_retries),
        )
    except Exception as e:
        st.error(f"Configuración inválida: {e}")
        st.stop()

    template = MappingTemplate(body_template=body_template if has_body else "")

    # Parsear archivo completo (sin límite de preview)
    try:
        full_pr = parse_file_full(st.session_state.file_bytes, st.session_state.filename)
        df_full = full_pr.dataframe
    except ParseError as e:
        st.error(f"Error al leer archivo completo: {e}")
        st.stop()

    st.session_state.stop_flag = [False]
    st.session_state.is_running = True
    st.session_state.live_log = []
    st.session_state.execution_result = None

    total_rows = len(df_full)
    progress_bar = st.progress(0, text="Iniciando...")
    log_placeholder = st.empty()

    completed_results: list[RowResult] = []

    def progress_callback(current: int, total: int, row_result: RowResult) -> None:
        completed_results.append(row_result)
        pct = current / total
        status_txt = f"Procesando fila {current}/{total}..."
        progress_bar.progress(pct, text=status_txt)

    # Ejecución en el thread principal (asyncio.run)
    from lib.executor import run_execution

    execution_result = run_execution(
        df=df_full,
        config=config,
        template=template,
        progress_callback=progress_callback,
        stop_flag=st.session_state.stop_flag,
        max_concurrent=int(max_concurrent),
    )

    st.session_state.execution_result = execution_result
    st.session_state.is_running = False
    progress_bar.progress(1.0, text="Completado.")
    st.rerun()

# Mostrar live log y resultados finales
if st.session_state.execution_result is not None:
    result: ExecutionResult = st.session_state.execution_result
    summary = build_summary(result)

    st.subheader("Resultado")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total procesadas", summary["total_rows"])
    mc2.metric("Exitosas", summary["successful"])
    mc3.metric("Fallidas", summary["failed"])
    mc4.metric("Tiempo promedio", f"{summary['avg_duration_ms']} ms")

    # Tabla de resultados
    with st.expander("Detalle de resultados", expanded=True):
        rows_data = [
            {
                "Fila": r.row_index,
                "Status": r.status_code or "—",
                "OK": "✓" if r.success else "✗",
                "Duración (ms)": r.duration_ms,
                "Error": r.error or "",
                "Response (truncado)": (r.response_body or "")[:100],
            }
            for r in result.results
        ]
        if rows_data:
            st.dataframe(pd.DataFrame(rows_data), width="stretch")

    # Descarga
    csv_bytes = to_csv_bytes(result)
    st.download_button(
        label="Descargar resultados CSV",
        data=csv_bytes,
        file_name="resultados_ejecucion.csv",
        mime="text/csv",
    )
