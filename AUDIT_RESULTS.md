# Audit results — 2026-10-15

Evidence is limited to the current workspace run. No PostgreSQL server or Docker daemon was reachable during this audit, so PostgreSQL-backed gates and a live demo are not claimed as passing.

**API follow-up:** the requested versioned endpoints were added after the initial audit snapshot. `python -m compileall -q app scripts tests` and OpenAPI route inventory were run after the changes; `docker compose config --quiet` still passes. Ruff is not installed, so its lint/format commands could not run. The PostgreSQL suite was subsequently rerun through the host-mapped port shown by the user and passed all seven tests.

| Gate | Status | Evidence | Remaining action |
|---|---|---|---|
| Versioned routes and request/response contract | PASS (source/OpenAPI review) | `app/api/orders.py`, `app/api/products.py`, `app/api/events.py`, `app/main.py`, `app/schemas.py`; [API_CONTRACT.md](API_CONTRACT.md) | Live HTTP verification requires DB |
| Daily report and accepted-order feed | PASS (source/OpenAPI review) | `app/reporting.py`, `app/api/events.py`; event feed is independent of `processed_at` | Live pagination verification requires DB |
| Schema and transactional order/outbox implementation | PASS (source review) | `app/db/models.py`, `app/orders/service.py`: unique order_ref, FK/checks, price snapshots, one transaction | Blank-DB run unavailable now |
| Worker recovery/idempotency/concurrency design | PASS (source review) | `app/outbox/worker.py`, `app/inventory/service.py`: row lock with SKIP LOCKED, guarded decrement, application ledger and acknowledgement in one transaction | Runtime/replay gates need PostgreSQL |
| Python syntax compilation | PASS | `python -m compileall -q app scripts tests` exit 0 | None |
| OpenAPI endpoint inventory | PASS | Imported `app.main.app` and enumerated routes; every requested method/path is present | Runtime database behavior remains unverified |
| Ruff lint and formatting | NOT RUN | `python -m ruff ...` reports `No module named ruff` | Install dev requirements, then run the README commands |
| Automated suite | PASS | `$env:TEST_DATABASE_URL='postgresql+psycopg2://mrd:mrd-local@localhost:64670/mrd_orders'; python -m pytest -q` → **7 passed** | Tests wrote rows to the configured database; use a separate test DB for isolation |
| Compose configuration | PASS (configuration only) | `docker compose config --quiet` exit 0 | Build/start unavailable because Docker Engine pipe denied |
| Compose build/start and Postman run | BLOCKED | `docker info` reports permission denied connecting to `npipe:////./pipe/docker_engine` | Start Docker Desktop with engine access; run README flow |
| Seed/burst/outage scripts | PASS (source review); NOT RUN | `scripts/seed.py`, `scripts/burst_demo.py`, `scripts/outage_demo.py` | Requires live DB/API and worker |
| Video | NOT DONE | A narration guide is included; no recording artifact exists | Record 5–10 minute demonstration |
| GitHub publication | NOT DONE | Workspace ownership prevents `git status` without changing global safe-directory config; no push attempted | Handle repository publishing separately |

## Unresolved verification

- The PostgreSQL integration suite, clean database initialization, live worker pause/resume, and exact stock outcomes were not executed in this environment.
- `migrations/` contains only `.gitkeep`; schema setup uses `Base.metadata.create_all` via `python -m scripts.init_db`, not versioned migrations.
- Compose stack config is valid, but image build/start and Postman execution remain unverified.
- The assignment's video deliverable still requires a human screen recording.
