# OpsPilot AI

An AI agent that investigates application incidents: it reads the submitted logs,
retrieves relevant runbooks, calls diagnostic tools, proposes a likely root cause and
recommends remediation that a human must approve before anything sensitive happens.

The project is built in small, reviewable phases. See "Status" below.

## Status

- Phase 1: FastAPI skeleton with a health endpoint.
- Phase 2: Postgres via SQLAlchemy, incident create/read/list endpoints.
- Phase 3: three deterministic diagnostic tools over local mock data.
- Phase 4: LangGraph investigation workflow (classify, evidence, analyze, validate, recommend).
- Phase 5: runbook chunking, embeddings, pgvector retrieval, retrieval wired into the graph.
- Phase 6: background investigations, persisted results, LangGraph checkpoints, approval gate.
- Phase 7: fixed incident evaluation set, regression tests, measured retrieval/quality numbers.
- Phase 8: LangSmith tracing and Docker Compose deployment files.
- Operator console: a Reflex UI in `frontend/` over the existing API (separate app, not a phase).

Automatic remediation execution is out of scope.

## Run locally

Postgres 16 with the `vector` extension is required; the runbook index lives there.

```bash
python3 -m venv .venv     # Python 3.11-3.13
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env      # set DATABASE_URL, OPENAI_API_KEY or LLM_PROVIDER=mock
python -c "import app.models; from app.database import init_db; init_db()"   # schema first
python -m app.retrieval   # chunk and embed runbooks/ into pgvector
uvicorn app.main:app --reload
```

### Local Postgres on this machine

A self-contained Postgres 16.2 + pgvector 0.6.2 cluster is installed under
`~/.local/share/opspilot-pg` (no root required). Start and stop it with:

```bash
./scripts/start-db.sh
./scripts/stop-db.sh
```

`.env` already points at `postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot`,
and the runbooks are indexed, so `python -m app.retrieval` is only needed after editing
files in `runbooks/`.

`requirements.txt` is the runtime set used by the container; `requirements-dev.txt` adds pytest
and httpx. Without Docker, point `DATABASE_URL` at any Postgres 16 instance that allows
`CREATE EXTENSION vector`; the Compose setup is under [Deployment](#deployment-docker-compose).

The extension and tables are created at startup (`init_db`). Alembic goes in once the schema
stops changing. Interactive API docs: `http://127.0.0.1:8000/docs`.

## Operator console (Reflex)

`frontend/` is a Reflex app that drives the API: create incidents, run investigations,
watch evidence and remediation, and approve or reject sensitive actions. It talks to
the API server-side, so no CORS is involved.

```bash
cd frontend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
reflex run          # http://localhost:3000, Reflex backend on 8001
```

Start the API on 8000 first. See [frontend/README.md](frontend/README.md) for the two
environment variables and the panel walkthrough.

## API

| Method | Path                              | Purpose                                            |
| ------ | --------------------------------- | -------------------------------------------------- |
| GET    | `/health`                         | Liveness check                                     |
| POST   | `/incidents`                      | Create an incident (title, severity, service, logs) |
| GET    | `/incidents`                      | List incidents; filter by `status`, `severity`, `service`; page with `limit`, `offset` |
| GET    | `/incidents/{id}`                 | One incident including logs and the last investigation result |
| POST   | `/incidents/{id}/investigate`     | Start the agent in the background (`202`)          |
| GET    | `/incidents/{id}/investigation`   | Investigation state, evidence, runbooks, diagnosis, remediation, approval |
| POST   | `/incidents/{id}/approval`        | Approve or reject pending sensitive actions (`X-API-Key`) |

```bash
curl -X POST http://127.0.0.1:8000/incidents \
  -H 'content-type: application/json' \
  -d '{"title":"Checkout API 500s","severity":"high","service":"checkout-api","logs":"ERROR pool exhausted"}'
```

`diagnosis`, `evidence`, `runbooks`, and `remediation` stay empty until an investigation runs.

## Diagnostic tools

Plain functions in `app/tools.py`, no framework wrapping and no real infrastructure. Mock
service and deployment data is fixed so the same incident always produces the same evidence.

| Function                                             | Returns up to the caller                                            |
| ---------------------------------------------------- | ------------------------------------------------------------------- |
| `search_logs(logs, pattern=None, level=None, limit=20)` | Matching lines with line numbers, parsed level and timestamp, level counts, truncation flag |
| `check_service_health(service)`                       | Registry record, or `known: false` when the service is not in the mock registry |
| `get_recent_deployments(service, hours=72, now=None)` | Deployments inside the window, newest first                         |

```bash
python -c "
from app.tools import search_logs
print(search_logs('2026-10-19T10:02:11Z ERROR pool exhausted', level='error'))
"
```

Logs are parsed as data only. Nothing from the log text is executed, evaluated, or treated as
an instruction, and messages are truncated to 300 characters before they reach a prompt.

## Runbooks (retrieval)

`runbooks/*.md` are the only knowledge base: database connections, high latency, and service
unavailability. Retrieval is a straight nearest-neighbour lookup; there is no agentic RAG loop.

```bash
python -m app.retrieval
# {'documents': 3, 'chunks': 18, 'added': 18}
```

- Chunks follow the markdown headings, and sections longer than 1200 characters are split with
  100 characters of overlap.
- Chunk ids are content hashes, so re-running ingestion does not duplicate anything. Chunks
  whose text changed or disappeared are deleted, so stale advice cannot be retrieved.
- `retrieve_runbooks(query, limit=3)` returns chunks within `RUNBOOK_MAX_DISTANCE` of the query.
  If everything is farther away, it returns `[]` and the agent is told "No runbooks matched this
  incident." Nothing is padded in.
- The agent builds its query from the title, description, category, service, and the first
  error lines from `search_logs`, so retrieval sees the same symptoms the analysis does.
- Runbook text is reference material. The validator prompt says so explicitly: a runbook can
  justify a response, but it cannot prove that an event happened.

Measured with the offline mock embedder (`EMBEDDING_PROVIDER=mock`), against the three runbooks:

| Query | Top result | Distance |
| ----- | ---------- | -------- |
| checkout 500s, pool exhausted, timeouts | `database_connection.md` | 0.51 |
| p99 latency high, requests slow | `high_latency.md` | 0.66 |
| 503, health checks failing | `service_unavailable.md` | 0.58 |
| how to bake sourdough bread | none | 0.88 |
| office printer out of toner | none | 0.82 |

The default cutoff of 0.75 sits in that gap. It is configuration, not a constant: OpenAI
embeddings produce different score spreads, so measure before trusting it.

Embeddings come from `EMBEDDING_PROVIDER=openai` by default. `EMBEDDING_PROVIDER=mock` is a
deterministic hashed bag-of-words vector used offline; it is not a real embedding model. Changing
`EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS` changes the vector width, so the `runbook_chunks`
table has to be dropped and rebuilt.

## Investigation agent

`app/agent.py` holds one bounded LangGraph workflow. Evidence gathering is deterministic tool
calls; the model is only used for judgement.

```
START → classify ─┬→ END (model failed)
                  └→ gather_evidence → find_runbooks → analyze ─┬→ END (model failed)
                                                                └→ validate ─┬→ gather_evidence
                                                                             └→ recommend ─┬→ END (model failed)
                                                                                           └→ prepare_approval → request_approval → END
```

- State is a typed `InvestigationState`. Every node returns the fields it changed.
- `observed` and `hypotheses` are separate fields, and a diagnosis is only recorded when the
  validator accepts a cause with evidence behind it. Otherwise the run ends as `escalated`
  with no remediation, which is the honest outcome for thin evidence.
- Runbook retrieval is built from observed text (title, description, service, log lines) and
  deliberately excludes the model's category, so a hypothesis cannot steer which evidence it sees.
- Bounded execution: at most two evidence rounds, `recursion_limit` on the graph, model
  timeouts and retries from `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES`.
- Any action that touches a running system (restart, rollback, scale, delete, failover) is
  marked `requires_approval` even if the model did not ask for approval.
- A malformed model answer raises `LLMError`, the run ends as `failed` with the reason in
  `errors`, and nothing is invented to fill the gap.

Run one investigation without an API key:

```bash
LLM_PROVIDER=mock python -c "
from app.agent import investigate
result = investigate({
    'id': 'b'*32, 'title': 'Checkout API 500s', 'description': '', 'service': 'checkout-api',
    'severity': 'high',
    'logs': '2026-10-19T10:02:11Z ERROR pool exhausted: connection timeout after 5000ms',
    'reference_time': '2026-10-19T12:00:00+00:00',
})
print(result['status'], result['diagnosis'])
"
```

With the mock recommendation, the run pauses at `awaiting_approval` because it proposes a
rollback. Approving it means calling the approval endpoint (or `resume_investigation`).

`LLM_PROVIDER=mock` returns fixture replies for offline runs and tests. It is never used
implicitly: with `LLM_PROVIDER=openai` and no `OPENAI_API_KEY`, the run fails with a clear
error instead of falling back to fixtures.

## Investigations and approvals

`POST /incidents/{id}/investigate` returns `202` and runs the graph in a background task; the
caller polls `GET /incidents/{id}/investigation`.

```
created ──investigate──> investigating ──> awaiting_approval ──approve──> completed
                                     │                    └─────reject───> rejected
                                     ├──> escalated   (evidence too thin)
                                     └──> failed      (model or tool error)
```

- Starting is only allowed from `created` or `failed`; a retry clears the previous result so
  old and new evidence cannot mix.
- When any recommended action is sensitive, `request_approval` pauses the graph with a
  LangGraph `interrupt()`. The incident is stored as `awaiting_approval` with
  `approval_status: pending`, the diagnosis, and the actions that need sign-off.
- `POST /incidents/{id}/approval` takes `{"approved": true|false, "comment": "..."}` and the
  `X-API-Key` header. The key is compared to `APPROVAL_API_KEY` with `compare_digest`: missing
  or wrong is `401`, no key configured is `503`. The recorded actor comes from
  `APPROVAL_ACTOR`; a second decision on the same incident is `409`.
- Approving marks sensitive actions `"approval": "approved"` and closes the incident as
  `completed`; rejecting marks them `"rejected"` and sets `rejected`. **Nothing is executed in
  either case** — this version has no infrastructure integration by design.
- Read-only recommendations do not pause the run; it finishes as `completed` directly.

```bash
curl -X POST http://127.0.0.1:8000/incidents/$ID/approval \
  -H 'content-type: application/json' \
  -H "X-API-Key: $APPROVAL_API_KEY" \
  -d '{"approved": true, "comment": "rolling back"}'
```

### Checkpoints

LangGraph checkpoints are what make a paused approval resumable, so they need durable storage:

- Postgres deployments use `PostgresSaver` with `CHECKPOINT_DATABASE_URL` (falls back to
  `DATABASE_URL`, converted from a SQLAlchemy URL to a psycopg DSN).
- `checkpointer.setup()` runs on the first investigation and creates LangGraph's checkpoint
  tables. No extra service is needed; it uses the same database as the incidents.
- Verified locally: pause an investigation, restart the API process, then approve — the
  decision still resumes and completes.
- SQLite runs (the test default) use `InMemorySaver`. Approvals work inside one process, but a
  restart loses the paused run. That trade-off is intentional for tests only.

## Tracing (LangSmith)

Tracing is off by default and uses LangSmith only.

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2-...
LANGSMITH_PROJECT=opspilot        # optional, defaults to the SDK's default project
# LANGSMITH_ENDPOINT=...          # self-hosted LangSmith only
```

- One investigation is one trace. The root run is `investigate <service>`, tagged
  `opspilot` and `severity:<level>`, with `incident_id` and `service` metadata. LangGraph also
  records `thread_id`, which is the incident id. Every graph node, model call, retrieval, and
  tool call becomes a child run, so a slow or failing step is visible without extra logging.
- `LANGSMITH_TRACING=true` without `LANGSMITH_API_KEY` fails at startup with a clear
  `TracingError`. Losing traces silently would be worse than refusing to start.
- **Traces contain incident content, including the submitted logs.** That is the point of a
  trace, but it means enabling it sends that data to LangSmith. Do not enable it for incidents
  whose data may not leave the environment.
- I verified emission with a local collector endpoint, not the hosted service: the collector
  received the root run with the expected name, tags, and metadata, and the API key was not in
  the payload. There is no LangSmith account in this development environment, so no hosted
  trace was produced here.

## Deployment (Docker Compose)

`Dockerfile`, `docker-compose.yml`, and `.dockerignore` are included. Compose starts Postgres
with pgvector, ingests the runbooks once, then starts the API.

```bash
cp .env.example .env    # set POSTGRES_PASSWORD and APPROVAL_API_KEY; add provider keys
docker compose up --build
curl http://127.0.0.1:8000/health
```

- `db` is `pgvector/pgvector:pg16` with a named `pgdata` volume.
- `runbooks` runs `python -m app.retrieval` once and exits; `api` waits for it to succeed, so
  the vector index is never empty when the first incident arrives.
- `POSTGRES_PASSWORD` and `APPROVAL_API_KEY` are required (`${VAR:?}`); there are no default
  credentials.
- For an offline end-to-end run, set `LLM_PROVIDER=mock` and `EMBEDDING_PROVIDER=mock` in
  `.env`. With the default `openai` providers, a missing key fails the ingest step and the API
  does not start — intentionally, rather than serving a half-built index.
- `docker compose down -v` removes the database volume, including incidents and checkpoints.
- **Not executed here:** Docker is not installed in this development environment. The Compose
  YAML parses, but the first `docker compose up --build` on a machine with Docker is the real
  verification. Everything else below was run locally against Postgres.

## Evaluation

`eval.py` runs a fixed seven-case set from `tests/eval_cases.json` through the real pipeline and
counts outcomes. It never estimates: every score is `passed / total` from the run. It also
re-ingests the runbooks first, so the retrieval numbers are measured against the current index.

```bash
DATABASE_URL=postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot \
LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock python eval.py
```

Metrics:

| Metric | What it checks |
| ------ | -------------- |
| Classification accuracy | Returned category equals the case's expected category. |
| Diagnosis keywords | Expected root-cause words appear in the diagnosis. |
| Runbook hit@1 | The expected runbook is the first chunk returned; cases that should match nothing return nothing. |
| Task completion | The run ends as the expected terminal state (`awaiting_approval`/`completed` for diagnosable cases, `escalated` for thin evidence). |
| Approval gating | A run pauses for approval exactly when it proposes a sensitive action. |
| Evidence coverage | All four tool results are present and none failed. |

The cases cover pool exhaustion, a 503 outage, a latency regression, two thin-evidence incidents,
a log line containing prompt-injection text, and a warning-only pool-pressure incident.

The harness prints the model provider it used, and that matters. The recorded run below used the
`mock` provider, so the two model-dependent metrics measure the fixtures, not model quality; they
will change with a real key. Retrieval, completion, gating, and evidence are real pipeline
behaviour either way.

```
model provider: mock
runbook index: {'documents': 3, 'chunks': 18, 'added': 0}

metric                              score
classification accuracy (model)     3/7 (43%)
runbook hit@1                       5/7 (71%)
task completion                     5/7 (71%)
approval gating                     5/7 (71%)
evidence coverage                   7/7 (100%)
diagnosis keywords (model)          3/7 (43%)
```

Reading the misses: the mock model classifies every incident as `database_connection` and returns
the same pool-saturation diagnosis, so it misses the search/latency cases and never escalates the
thin-evidence ones (it diagnoses them anyway). Retrieval also misses two of them because the mock
embedder puts the correct chunks at 0.80–0.86, above the `0.75` cutoff; this is the known
limitation of the offline hashed embedder, not a tuning target for this dataset.

`tests/test_regression.py` replays the same seven cases as ordinary tests and asserts the
structural invariants: a legal terminal state, all four evidence sources present without tool
errors, approval exactly when a sensitive action is proposed, no invented "executed" fields, an
unknown service left unknown, and the hostile log line staying evidence rather than becoming an
action. It does not encode the mock model's diagnoses.

## Tests

```bash
pytest        # 73 passed, 9 skipped without Postgres
```

The suite runs on SQLite by default, which covers the API, tools, agent, approval flow, tracing
wiring, and the regression dataset. The nine runbook retrieval tests need pgvector and are
skipped unless you point the suite at Postgres:

```bash
TEST_DATABASE_URL=postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot pytest
# 82 passed
```

## Configuration

All configuration comes from environment variables, loaded from `.env` when present
(see `.env.example`). No secrets are committed, and none belong in code.

## Notes and limitations

- Incident `id` values are 32-character UUID hex strings, not Postgres `uuid` columns, so the
  same models run on SQLite in tests and Postgres in deployment.
- Enums (`severity`, `status`) are stored as short strings rather than Postgres enum types to
  keep migrations and filters simple.
- Logs are accepted as untrusted text, capped at 200k characters. Nothing in the logs is
  executed or interpreted as instructions.
- Retrieval is single-query nearest-neighbour search. It will not catch paraphrases that share
  no vocabulary with the runbooks, and the cutoff needs re-measuring whenever the embedding
  model changes.
- The runbook embeddings and the incident rows share one database, so retrieval tests only run
  against Postgres; SQLite is used for everything that does not need vector search.
- Approval authentication is a single shared operator key, not per-user identity or roles.
  There is no audit trail beyond `approved_by` / `approved_at`.
- Schema changes still rely on `create_all`. There is no Alembic yet, so upgrading an existing
  development database means dropping and recreating the tables.
- Approving an action records the decision. It does not execute anything against infrastructure.
- Evaluation scores printed under `LLM_PROVIDER=mock` measure fixtures. Quote diagnosis and
  classification numbers only from a run with a real model provider.
- LangSmith traces include the submitted incident text, logs included, and were verified against
  a local collector rather than the hosted service (no key here). The Docker image and Compose
  stack were written but could not be built in this environment; Docker is not installed.
