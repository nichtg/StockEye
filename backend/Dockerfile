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
# FORWARDED_ALLOW_IPS lists the only addresses whose X-Forwarded-For/-Proto uvicorn believes;
# from anyone else the headers are ignored, so a direct client cannot spoof its IP past the
# rate limiter. The default is the subnet docker-compose.yml pins for the stack. For any other
# topology set it to the address of whatever proxy fronts the API, never "*".
ENV PATH="/app/.venv/bin:$PATH" \
    STOCKEYE_ENVIRONMENT=prod \
    STOCKEYE_FINBERT_MODEL_DIR=/app/models/finbert \
    FORWARDED_ALLOW_IPS=172.28.0.0/16
USER stockeye
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"
# `sh -c` expands the variable; `exec` keeps uvicorn as PID 1 so it receives stop signals.
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
