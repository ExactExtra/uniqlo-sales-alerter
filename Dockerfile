# ---- build stage ----
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir .

# ---- runtime stage ----
FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uniqlo_sales_alerter"]
