# genpipe

Generation job pipeline. Workspaces submit generation jobs through the HTTP
API, a worker hands each job to the upstream provider (Acme Generative API)
and the provider reports the result back through a webhook. Workspaces pay
for generations with prepaid credits.

The task description is in [TASK.md](TASK.md).

## Architecture

```
client ──HTTP──> api (FastAPI) ──AMQP──> worker (Celery) ──HTTP──> provider
                   │   ▲                      │                        │
                   ▼   └──────────────── webhook ◄─────────────────────┘
               PostgreSQL <───────────────────┘
               Redis (rate limiting, model catalog cache)
```

| Component | Where | Notes |
|---|---|---|
| HTTP API | `app/api/` | FastAPI. Auth by `X-API-Key`, one key per workspace |
| Worker | `app/worker/` | Celery on RabbitMQ. `process_job` starts generations, `reap_stuck_jobs` runs every minute from beat |
| Billing | `app/billing.py` | Balance on `workspaces.credits`, ledger in `credit_transactions` |
| Provider client | `app/provider/` | See [docs/provider_api.md](docs/provider_api.md) |
| Provider simulator | `provider_mock/` | Stand-in for the third-party API. Not under review |

### Job lifecycle

1. `POST /v1/jobs` validates the request, prices the job and stores it as `queued`.
2. The worker picks the job up, charges the workspace and creates a generation
   at the provider. The job becomes `processing`.
3. The provider calls `POST /v1/webhooks/provider`. The job becomes `succeeded`
   (with `output_urls`) or `failed` (and the credits are refunded).
4. Jobs that stay `processing` for more than 15 minutes are failed and refunded
   by `reap_stuck_jobs`.

### Guarantees

- A job is charged exactly once and refunded in full if it does not succeed.
- Webhooks are authenticated with the provider's HMAC signature and
  deduplicated by event id.
- Jobs and ledger entries are visible only to the workspace that owns them.

## Running

Requires Docker with the compose plugin.

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| API (OpenAPI UI at `/docs`) | http://localhost:8000 |
| Provider simulator | http://localhost:9000 |
| RabbitMQ management (guest/guest) | http://localhost:15672 |

The API container creates the tables and two demo workspaces on start:

| Workspace | API key | Credits |
|---|---|---|
| Alpha Studio | `ws_alpha_demo_key` | 500 |
| Beta Labs | `ws_beta_demo_key` | 500 |

```bash
curl -s -X POST localhost:8000/v1/jobs \
  -H 'X-API-Key: ws_alpha_demo_key' -H 'Content-Type: application/json' \
  -d '{"model": "flux-fast", "prompt": "a lighthouse at dawn", "num_outputs": 2}'

curl -s localhost:8000/v1/jobs -H 'X-API-Key: ws_alpha_demo_key'
curl -s localhost:8000/v1/credits -H 'X-API-Key: ws_alpha_demo_key'
```

The source tree is mounted into the containers; the API reloads on change,
the worker needs `docker compose restart worker`.

The simulator misbehaves on purpose, within what the provider documents. The
`MOCK_*` variables in `docker-compose.yml` control how often.

## Tests

```bash
docker compose run --rm tests
```

Tests run against a separate `genpipe_test` database in the same PostgreSQL
container. Celery tasks run inline and the provider is replaced with a fake
(`tests/conftest.py`), so RabbitMQ, Redis and the simulator are not needed.

## API

| Method | Path | |
|---|---|---|
| POST | `/v1/jobs` | Submit a job |
| GET | `/v1/jobs` | List the workspace's jobs (`status`, `limit`, `offset`) |
| GET | `/v1/jobs/{id}` | One job |
| GET | `/v1/credits` | Balance |
| GET | `/v1/credits/transactions` | Ledger (`job_id`, `limit`, `offset`) |
| GET | `/v1/models` | Models, prices, availability |
| POST | `/v1/webhooks/provider` | Provider callbacks |

There are no schema migrations in this repository: tables are created with
`create_all`. If you change the schema, recreate the database
(`docker compose down -v`) and say in your notes how you would migrate a live
one.
