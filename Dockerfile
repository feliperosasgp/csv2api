FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install deps first (layer cache)
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# App code
COPY --chown=appuser:appuser app.py .
COPY --chown=appuser:appuser lib/ ./lib/

USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.fileWatcherType=none"]
