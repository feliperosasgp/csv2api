# CLAUDE.md — CSV Bulk API Caller (Streamlit + Python)

## Qué es esto

Una app local en Streamlit + Python que permite:

1. **Subir un archivo** CSV o Excel
2. **Previsualizar** las filas y columnas del archivo
3. **Configurar un endpoint HTTP** (URL, método, headers, auth)
4. **Mapear columnas del archivo a campos de un JSON body** usando un template builder visual
5. **Ejecutar requests fila por fila** contra el endpoint
6. **Ver resultados en tiempo real** (progress bar, status codes, response bodies, errores)
7. **Exportar un reporte** de resultados (CSV con status por fila)

No existe una herramienta open source standalone que haga exactamente esto. Esta app llena ese gap.

---

## Stack

- **Python 3.11+**
- **Streamlit** — UI
- **Pandas** — parsing CSV/Excel
- **httpx** — HTTP client async (preferido sobre requests por soporte async + timeouts granulares)
- **Pydantic** — validación de config (endpoint, headers, JSON template)

No usar frameworks adicionales. No usar bases de datos. Todo corre en memoria. Sin Docker por ahora (es para correr local con `streamlit run`).

---

## Estructura del proyecto

```
csv-bulk-api-caller/
├── app.py                  # Entry point: streamlit run app.py
├── requirements.txt
├── README.md
├── lib/
│   ├── __init__.py
│   ├── parser.py           # CSV/Excel parsing con Pandas
│   ├── mapper.py           # Template engine: columna → campo JSON
│   ├── executor.py         # HTTP execution engine (async, con rate limiting)
│   ├── models.py           # Pydantic models (EndpointConfig, MappingTemplate, ExecutionResult)
│   └── exporter.py         # Export resultados a CSV
└── tests/
    ├── test_parser.py
    ├── test_mapper.py
    └── test_executor.py
```

---

## Detalle funcional por módulo

### 1. `lib/parser.py` — File Parser

- Acepta `.csv`, `.xlsx`, `.xls`
- Usa `pandas.read_csv()` y `pandas.read_excel()`
- Detecta encoding automáticamente con `chardet` (fallback a utf-8)
- Retorna un `DataFrame` limpio + lista de nombres de columnas
- Maneja edge cases: archivos vacíos, sin headers, con filas en blanco
- Límite configurable de filas para preview (default: 100)

### 2. `lib/models.py` — Pydantic Models

```python
class EndpointConfig(BaseModel):
    url: str                          # Soporta variables de columna: https://api.com/users/{id}
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    headers: dict[str, str] = {}      # Key-value, soporta variables: {"Authorization": "Bearer {token}"}
    timeout_seconds: int = 30
    rate_limit_ms: int = 100          # Delay entre requests (ms)
    max_retries: int = 0
    
class MappingTemplate(BaseModel):
    body_template: str                # JSON string con placeholders: {"name": "{nombre}", "email": "{correo}"}
    column_mapping: dict[str, str]    # {placeholder: columna_del_csv}

class RowResult(BaseModel):
    row_index: int
    status_code: int | None
    response_body: str | None
    error: str | None
    duration_ms: float

class ExecutionResult(BaseModel):
    total_rows: int
    successful: int
    failed: int
    results: list[RowResult]
```

### 3. `lib/mapper.py` — Template Mapper

- Toma una fila del DataFrame + el `MappingTemplate`
- Reemplaza placeholders `{column_name}` con valores de la fila
- El body_template es un JSON string con placeholders — se parsea DESPUÉS del reemplazo para validar JSON válido
- Los placeholders también aplican en la URL y en los headers (para auth tokens por fila, por ejemplo)
- Si un placeholder referencia una columna que no existe → error claro, no falla silenciosamente
- Valores nulos en la fila → se reemplazan con `null` en el JSON (no con string "None")

### 4. `lib/executor.py` — Execution Engine

- Usa `httpx.AsyncClient` para las requests
- Ejecución secuencial por defecto (una fila a la vez) con delay configurable entre requests
- Opción de concurrencia limitada (semaphore) para ejecución paralela: max 5 concurrent
- Cada request tiene timeout individual
- Retry logic con backoff exponencial (si max_retries > 0)
- Reporta progreso via callback (para la progress bar de Streamlit)
- NO falla si una fila falla — continúa con la siguiente y registra el error
- Cancelable: el usuario puede detener la ejecución mid-run

### 5. `lib/exporter.py` — Results Exporter

- Toma `ExecutionResult` y genera un CSV descargable
- Columnas: `row_index`, `status_code`, `response_body` (truncado), `error`, `duration_ms`
- También genera un summary: total, exitosos, fallidos, tiempo promedio

---

## UI Flow en Streamlit (app.py)

La app tiene un flujo lineal en una sola página, con secciones colapsables:

### Sección 1: Upload
- `st.file_uploader` para CSV/Excel
- Al subir, muestra preview del DataFrame (primeras 20 filas)
- Muestra info: total filas, columnas detectadas, tipos inferidos

### Sección 2: Endpoint Config
- Input para URL (text input)
- Selector de método HTTP (selectbox)
- Editor de headers como key-value pairs (columnas side by side con botón "+" para agregar)
- Inputs para timeout, rate limit delay, retries
- Checkbox "Dry run" — parsea y mapea sin ejecutar, muestra el request que se enviaría para la primera fila

### Sección 3: JSON Body Mapping
- Text area para el JSON template con placeholders `{column_name}`
- A la derecha (o debajo): lista de columnas disponibles del CSV como "chips" clickeables que insertan el placeholder
- Preview en vivo: muestra cómo se ve el JSON resuelto para la fila 1 del CSV
- Validación en vivo: marca si el template no es JSON válido después del reemplazo
- Nota: para métodos GET/DELETE, esta sección se oculta (no hay body)

### Sección 4: Execution
- Botón "Execute" prominente
- Progress bar con counter: "Processing row 45/200..."
- Live log: tabla que se actualiza con cada request completado (row, status, duration)
- Botón "Stop" para cancelar mid-run
- Al terminar: summary cards (total, success, failed, avg time)
- Botón "Download Results CSV"

---

## Reglas de implementación

1. **No guardar estado en disco.** Todo vive en `st.session_state`. Si el usuario recarga, pierde todo. Eso es aceptable.
2. **No auth propia.** Es una herramienta local, no necesita login.
3. **El JSON template es un string, no un form builder.** Es más flexible — el usuario escribe el JSON y usa `{placeholders}`. No necesitamos un GUI de mapeo campo por campo.
4. **Error handling es crítico.** La app NUNCA debe crashear. Errores de parsing, de red, de JSON inválido — todo se captura y se muestra amigablemente.
5. **El executor es async** pero Streamlit es sync. Usar `asyncio.run()` como bridge. No usar threading.
6. **UI limpia y funcional.** No over-designar. Streamlit vanilla sin custom CSS salvo ajustes mínimos de layout.
7. **No dependencias pesadas.** Solo Streamlit, pandas, httpx, pydantic, chardet. Nada más.
8. **Soportar templates anidados.** El body template puede ser JSON anidado: `{"user": {"name": "{nombre}", "contact": {"email": "{correo}"}}}` — el reemplazo es string-level antes del JSON parse, así que esto funciona gratis.
9. **Los placeholders en la URL también se resuelven.** Ejemplo: `https://api.com/contacts/{hubspot_id}/update` toma el valor de la columna `hubspot_id` de cada fila.

---

## Configuración guardable (nice to have, fase 2)

- Permitir guardar/cargar configuraciones de endpoint + template como archivos JSON locales
- `st.download_button` para exportar config, `st.file_uploader` para importar
- Esto permite reusar configs sin reconfigurar cada vez

---

## Testing

- Tests unitarios con pytest
- `test_parser.py`: parseo de CSV con diferentes encodings, Excel, archivos vacíos
- `test_mapper.py`: reemplazo de placeholders, JSON anidado, valores nulos, columnas faltantes
- `test_executor.py`: mock HTTP responses, retry logic, timeout handling, rate limiting
- No tests de UI (Streamlit no se presta para eso fácilmente)

---

## Cómo correr

```bash
cd csv-bulk-api-caller
pip install -r requirements.txt
streamlit run app.py
```

Se abre en `http://localhost:8501`. Listo.

---

## Para el futuro (no implementar ahora)

- Docker compose para deployment compartido
- Presets de endpoints comunes (HubSpot, Salesforce, etc.)
- Autenticación OAuth2 flow
- Scheduling / cron de ejecuciones
- Modo "diff" — comparar resultados entre ejecuciones
