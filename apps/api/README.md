# apps/api

FastAPI service for the music intelligence pipeline. Dependencies are managed by
[uv](https://docs.uv.dev) from `pyproject.toml` (single source of truth - there is
no `requirements.txt`).

```bash
# from the repo root
pnpm dev:api                      # uvicorn --reload on http://127.0.0.1:8000
pnpm lint:api                     # ruff check
pnpm format:api                   # ruff format
pnpm test:api                     # pytest

uv run --project apps/api <cmd>   # anything else
```

Environment variables live in `.env` (see `.env.example`). Layout:

| Path             | Responsibility                                          |
| ---------------- | ------------------------------------------------------- |
| `app/api/routes` | HTTP layer only - request/response wiring               |
| `app/core`       | Settings, connection handling, UUIDv7 ids               |
| `app/models`     | One module per table: row dataclass + its statements    |
| `app/schemas`    | Pydantic request/response contracts                     |
| `app/services`   | Business logic (`queue.py`: the analysis state machine) |
| `app/workers`    | The standalone analysis worker (stages, runner)         |
| `tests`          | Pytest suite (`pythonpath = ["."]`, imports `app.*`)    |

The tests split in two: unit tests that need nothing, and database tests
(`test_schema.py`, `test_rls.py`, `test_queue.py`, `test_upload_flow.py`,
`test_upload_results.py`, `test_api_routes.py`) that need a migrated database and
skip themselves unless `MYBAND_TEST_DATABASE_URL` points at one.

```bash
pnpm dlx supabase@latest start    # from the repo root
$env:MYBAND_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
pnpm test:api
```

## Endpoints

Every route needs `Authorization: Bearer <supabase access token>` and scopes its
queries by that token's `sub`. The full contract - request and response bodies,
status codes, error codes - is in `docs/upload-flow.md`.

| Method | Path                | What it does                                           |
| ------ | ------------------- | ------------------------------------------------------ |
| POST   | `/uploads/presign`  | Reserve an object and return the URL that fills it     |
| POST   | `/uploads/complete` | Confirm what landed; create the song and queue the job |
| GET    | `/uploads/{id}`     | One upload, and where it got to                        |
| GET    | `/songs`            | The caller's library, with each song's current job     |
| GET    | `/songs/{id}`       | One song and its most recent analysis                  |
| GET    | `/jobs/{id}`        | One analysis job                                       |
| GET    | `/health`           | Liveness, no token required                            |

Storage has to exist before the first upload, and `supabase start` provides it:
point `R2_ENDPOINT_URL` at its S3 endpoint and create the bucket. `docs/upload-flow.md`
has the values and the SQL.
