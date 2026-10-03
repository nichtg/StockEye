# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY app ./app
COPY scripts ./scripts
RUN uv sync --locked --no-dev
# Bake the FinBERT ONNX model into the image so containers start without network access.
RUN uv run --no-dev python scripts/download_finbert.py --dest models/finbert

FROM python:3.13-slim-bookworm
WORKDIR /app
RUN useradd --create-home --uid 10001 stockeye
COPY --from=build --chown=stockeye:stockeye /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    STOCKEYE_ENVIRONMENT=prod \
    STOCKEYE_FINBERT_MODEL_DIR=/app/models/finbert
USER stockeye
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
