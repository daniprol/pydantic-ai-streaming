# Streaming Chat API

FastAPI backend for the multi-flow streaming chat demo.

## Run locally

```sh
uv sync
uv run uvicorn streaming_chat_api.main:app --reload --port 8000
```

Run the Temporal worker in a separate terminal:

```sh
uv run python -m streaming_chat_api.temporal_worker
```
