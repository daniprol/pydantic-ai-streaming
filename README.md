# Streaming Chat Workspace

This repository now contains a pnpm workspace frontend plus a uv workspace for the Python backend and libraries:

- `apps/web`: Vite + React + Vercel AI SDK UI
- `apps/api`: FastAPI + PydanticAI + SQLAlchemy + Alembic
- `packages/pydantic-ai-absurd`: lightweight Absurd durable execution wrapper for PydanticAI

## Environment files

- API secrets and Azure OpenAI configuration belong in `apps/api/.env`
- Frontend non-secret config belongs in `apps/web/.env`
- `apps/api/.env.example` and `apps/web/.env.example` are the templates

## Local development

Backend:

```sh
uv sync --all-packages
uv run --package streaming-chat-api uvicorn streaming_chat_api.main:app --reload --port 8000
```

Absurd library:

```sh
uv run --package pydantic-ai-absurd pytest packages/pydantic-ai-absurd/tests -s
uv build --package pydantic-ai-absurd --no-sources
```

Frontend:

```sh
pnpm install
pnpm --filter @streaming-chat/web dev
```

Full stack with infrastructure:

```sh
docker compose up --build
```

## Testing

- Backend: `pytest` with unit and integration tests under `apps/api/tests`
- Frontend: `vitest` for unit/integration tests and Playwright for browser e2e
- Preferred workflow: write or update a failing test before implementing a new behavior or bugfix
- Real model tests are marked `llm` and excluded by default; run them explicitly with `pnpm test:api:llm`
- For new AI Elements UI pieces, use the CLI instead of hand-scaffolding:

```sh
pnpm --filter @streaming-chat/web ai-elements:add
```

## Services

- Web: `http://localhost:5173`
- API: `http://localhost:8000`
- Temporal UI: `http://localhost:8233`

Copy the example env files in each app before running outside Docker.
