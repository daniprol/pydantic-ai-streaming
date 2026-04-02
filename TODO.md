# TODO

## Pending

- Add true full-stack browser e2e tests that run `web` and `api` together and verify:
  - chat creation from the browser
  - streamed responses
  - Postgres-backed conversation/message persistence
  - replay resume after disconnect
- Extend browser e2e coverage beyond the current shell smoke test to cover all four flows: `basic`, `dbos`, `temporal`, and `dbos-replay`.
- Add compose-backed e2e wiring for durable flows so DBOS/Temporal behavior is verified end-to-end, not only through backend-level tests.

## Not Correctly Working Yet

- Current Playwright e2e only proves the frontend shell loads. It does not yet talk to a live backend stack.
- During the shell e2e run, Vite logged proxy errors to `127.0.0.1:8000` because the backend was not running in that browser-test environment.
- `pytest -q` is flaky in this shell because of a pytest capture/tmpfile issue. Normal pytest runs with `-s` are working and were used for verification.

## Nice Next Steps

- Add CI scripts/jobs that run:
  - backend default tests
  - backend `llm` tests as an opt-in/manual job
  - frontend Vitest
  - compose-backed Playwright e2e
