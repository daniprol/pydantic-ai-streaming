# Streaming Chat Workspace

This repository now contains a pnpm workspace frontend and a uv-managed FastAPI backend:

- `apps/web`: Vite + React + Vercel AI SDK UI
- `apps/api`: FastAPI + PydanticAI + SQLAlchemy + Alembic

## Environment files

- API secrets and Azure OpenAI configuration belong in `apps/api/.env`
- Frontend non-secret config belongs in `apps/web/.env`
- `apps/api/.env.example` and `apps/web/.env.example` are the templates

## Local development

Backend:

```sh
uv sync --project apps/api
uv run --project apps/api uvicorn streaming_chat_api.main:app --reload --port 8000
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

## Temporal search attributes

Temporal UI can group/filter chat turn workflows by conversation when each workflow is started with the same `ConversationId` search attribute.

Create the custom search attributes after the Temporal server is ready:

```sh
docker compose exec temporal temporal operator search-attribute create \
  --address temporal:7233 \
  --namespace default \
  --name ConversationId --type Keyword \
  --name ModelName --type Keyword \
  --name FlowType --type Keyword
```

Verify them:

```sh
docker compose exec temporal temporal operator search-attribute list \
  --address temporal:7233 \
  --namespace default
```

Search in Temporal UI with:

```text
ConversationId = "<conversation-id>"
```

Ways to run this setup after Temporal is ready:

1. Recommended for this repo: run the one-off `docker compose exec temporal ...` command above after `docker compose up -d`.
2. Add a one-shot init service in `docker-compose.yml` that waits for `temporal` to become healthy, then runs the same `temporal operator search-attribute create ...` command. This matches Temporal's docs style of using setup scripts/services for self-hosted initialization.
3. If you use the standalone Temporal dev server instead of the current Docker stack, you can pre-register attributes on startup with `temporal server start-dev --search-attribute "ConversationId=Keyword" --search-attribute "ModelName=Keyword" --search-attribute "FlowType=Keyword"`.

Example one-shot init service:

```yaml
temporal-init:
  image: temporalio/auto-setup:1.29.1
  depends_on:
    temporal:
      condition: service_healthy
  command:
    [
      "sh",
      "-lc",
      "temporal operator search-attribute create --address temporal:7233 --namespace default --name ConversationId --type Keyword --name ModelName --type Keyword --name FlowType --type Keyword || true",
    ]
  restart: "no"
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
