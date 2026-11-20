# OpsPilot operator console

A Reflex frontend for the OpsPilot AI API. It lists incidents, creates new ones,
starts investigations, streams their progress, and shows the evidence, runbooks,
diagnosis, remediation, and the approval gate.

The browser only renders the Reflex component tree. Every API call is made by the
Reflex backend (`opspilot_ui/state.py`) over HTTP, so there is no CORS setup and no
API key in the browser.

## Start the API first

```bash
cd ..                      # project root
./scripts/start-db.sh      # local Postgres 16 + pgvector
source .venv/bin/activate
uvicorn app.main:app --reload          # http://127.0.0.1:8000
```

## Run the console

```bash
cd frontend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
reflex run                 # UI http://localhost:3000
```

Reflex serves its own backend on **8001** (set in `rxconfig.py`) so it does not
collide with the API on 8000.

## Configuration

`frontend/.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPSPILOT_API_URL` | `http://127.0.0.1:8000` | Where the OpsPilot API runs |
| `OPSPILOT_APPROVAL_KEY` | empty | Prefills the `X-API-Key` field on the approval panel |

The key is only a convenience default; you can edit it in the UI before approving.
It must match `APPROVAL_API_KEY` in the API's `.env`.

## What each panel does

- **New incident** — title, service, severity, description, and logs. Logs are sent
  as untrusted evidence, exactly as the API expects.
- **Incidents** — filtered list; click a row to load it.
- **Detail** — status, severity, submitted logs, diagnosis, remediation actions
  (with a badge once decided), retrieved runbooks, raw evidence per tool, pipeline
  warnings, and a timeline.
- **Approval gate** — appears only while an incident is `awaiting_approval`. Approve
  or reject, optionally with a comment. Nothing is executed; the API records the
  decision.
- **Run investigation** — enabled only for `created`/`failed` incidents, matching
  the API's rule. The UI polls until the run settles.

## Layout

```
frontend/
├── rxconfig.py             # ports 3000/8001, plugins
├── requirements.txt
├── opspilot_ui/
│   ├── state.py            # all HTTP calls and UI state
│   └── opspilot_ui.py      # component tree
└── .env
```

## Notes

- Runbook retrieval needs the API to use Postgres with pgvector. The project `.env`
  points at the local cluster, so the Runbooks panel is populated. If you switch the
  API back to SQLite, investigations still complete but the panel stays empty and the
  API's retrieval error appears under **Pipeline warnings**.
- The console does not cache: **Refresh** reloads the list and the open incident.
