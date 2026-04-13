# CSV Bulk API Caller

A local Streamlit app that lets you upload a CSV or Excel file and fire HTTP requests **row by row** against any API endpoint — no code required.

Built for developers and ops teams who need to bulk-create, update, or delete records in any REST API using data from a spreadsheet.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Streamlit](https://img.shields.io/badge/streamlit-1.35%2B-red)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Upload CSV or Excel** — `.csv`, `.xlsx`, `.xls` with automatic encoding detection
- **Visual endpoint config** — URL, HTTP method, headers (with per-row placeholder support)
- **JSON body templating** — write a JSON template with `{column_name}` placeholders; the app resolves them per row
- **Live execution** — progress bar, live results table, stop button mid-run
- **Dry run mode** — preview the exact request for row 1 before firing anything
- **Retry & rate limiting** — configurable delay between requests, exponential backoff on failure
- **Limited concurrency** — up to 5 parallel requests via async semaphore
- **Export results** — download a CSV report with status codes, response bodies, and errors per row

---

## Quick Start

### Requirements

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

### Install & run

```bash
# Clone the repo
git clone https://github.com/your-username/csv-bulk-api-caller.git
cd csv-bulk-api-caller

# Create virtualenv and install dependencies
uv venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt

# Run the app
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## How It Works

### 1. Upload your file

Upload a CSV or Excel file. The app shows a preview of the first 20 rows and detects column names automatically.

### 2. Configure the endpoint

Set the target URL, HTTP method, and any headers. You can use `{column_name}` placeholders anywhere — in the URL, in header values, and in the body:

```
URL:     https://api.example.com/contacts/{hubspot_id}
Header:  Authorization: Bearer {api_token}
```

### 3. Write the JSON body template

Use `{column_name}` placeholders in a JSON template. Nested JSON is fully supported:

```json
{
  "name": "{full_name}",
  "email": "{email}",
  "address": {
    "city": "{city}",
    "country": "{country}"
  }
}
```

The app shows a live preview of the resolved JSON for row 1 and validates it in real time.

> For `GET` and `DELETE` requests, the body section is hidden automatically.

### 4. Execute

Click **Execute**. The app processes each row, shows progress, and updates a live results table. You can stop at any time with the **Stop** button.

When done, download the full results as a CSV with status codes, response bodies (truncated), errors, and duration per row.

---

## JSON Placeholder Rules

| Case | Behavior |
|------|----------|
| `{column_name}` exists in CSV | Replaced with the cell value |
| Cell value is empty / NaN | Replaced with `null` |
| `{column_name}` not in CSV | Error shown, row marked as failed |
| Placeholder in URL | Resolved before the request |
| Placeholder in header value | Resolved before the request |

---

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| Timeout | 30s | Per-request timeout |
| Delay between requests | 100ms | Rate limiting — delay after each request |
| Max retries | 0 | Retries on network error (exponential backoff) |
| Max concurrency | 1 | Parallel requests (max 5) |

---

## Running Tests

```bash
pytest tests/ -v
```

38 tests covering the parser, template mapper, and execution engine.

---

## Project Structure

```
csv-bulk-api-caller/
├── app.py              # Streamlit entry point
├── requirements.txt
├── lib/
│   ├── models.py       # Pydantic models
│   ├── parser.py       # CSV/Excel parsing
│   ├── mapper.py       # Template engine
│   ├── executor.py     # Async HTTP execution engine
│   └── exporter.py     # Results CSV export
└── tests/
    ├── test_parser.py
    ├── test_mapper.py
    └── test_executor.py
```

---

## Security Notes

- **No data is sent anywhere except the endpoint you configure.** The app runs entirely locally.
- **Never commit real CSV files** — they may contain PII or sensitive records. The `.gitignore` excludes all `.csv` and `.xlsx` files by default.
- API keys and tokens belong in the header fields of the UI, not in code or committed files.

---

## Roadmap

- [ ] Save/load endpoint configurations as JSON files
- [ ] Presets for common APIs (HubSpot, Salesforce, etc.)
- [ ] OAuth2 flow support
- [ ] Docker image for team sharing
- [ ] Diff mode — compare results across runs

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you'd like to change.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'feat: add my feature'`
4. Push and open a PR against `main`

---

## License

MIT
