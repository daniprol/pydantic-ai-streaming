FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/apps/api

COPY apps/api/pyproject.toml apps/api/uv.lock* ./
RUN uv sync --no-dev

COPY apps/api ./

RUN useradd --create-home appuser && chown -R appuser:appuser /workspace
USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "streaming_chat_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
