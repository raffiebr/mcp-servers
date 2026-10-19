FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data PORT=8000 \
    UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# --frozen: install exactly what uv.lock pins (the versions that were tested).
RUN uv sync --frozen --no-dev --no-cache

# Non-root user; /data is a host volume owned by uid 10001 (see vm-bootstrap.sh).
RUN useradd --uid 10001 --create-home app && mkdir -p /data && chown app /data
USER app

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["garmin-mcp"]
