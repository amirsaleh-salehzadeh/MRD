# Mr D Senior Python Engineer — Orders & Stock Core Flow

> **Purpose:** Implementation plan, project explanation, and progress tracker for Codex. This repository is a technical vetting assignment, not a production commerce platform.
>
> **Instructions for Codex:** Read this entire file before coding. Implement the checklist in order, update checkboxes as work is genuinely completed, note evidence (commands/test results) in the progress log, and do not mark unverified work as done. Keep the scope intentionally small. Use Python and PostgreSQL, run on Linux/macOS, and deliver a working local demo with `README.md` and `SOLUTION.md`.

## 1. Project explanation

Build a small transactional commerce backend that accepts customer orders, stores them durably, calculates totals using a snapshot of product prices, and decreases stock asynchronously. The API must keep accepting orders when stock processing is paused and automatically catch up after the worker resumes. A repeated `order_ref` must never create a second order or deduct stock twice.

The intended story is:

1. A client POSTs an order to an **Orders API**.
2. In **one PostgreSQL transaction**, the API stores the order, its price-snapshot line items, and an immutable `OrderAccepted` outbox event.
3. The API responds immediately with an order ID, total, and a status such as `PENDING_STOCK`.
4. An independently runnable **Stock Worker** polls unprocessed events from PostgreSQL.
5. The worker atomically updates inventory, records the event as applied, and changes the order to `STOCK_UPDATED`.
6. During a simulated worker pause, newly submitted orders accumulate safely in the outbox; on resume, the worker catches up.
7. A **daily report** endpoint provides total accepted orders, revenue, units sold by SKU, and current stock by SKU (**Option B**, chosen instead of Option A).

### Scope boundaries

- Implement **exactly two representative unhappy-path demonstrations**: (1) duplicate submissions and (2) paused worker with recovery and catch-up.
- No authentication, payment, cancellation, refunds, distributed broker, emails, cloud deployment, sophisticated reservations, or generalized retry framework.
- Validate basic request shape and SKU existence to keep the demo operable, but do not build additional unhappy-path demonstrations.
- Assume seeded inventory has enough stock for the supplied demo orders. Document that production would need an explicit insufficient-stock policy (reservation/rejection/oversell handling); do not silently permit negative stock.
- Keep Python dependencies few and familiar; favor clarity over frameworks and abstractions.

## 2. Architecture and design choices

```text
     POST /orders        GET /orders/{order_ref}
           |                     ^
           v                     |
    +-------------------------------+
    | Orders API (FastAPI)          |
    | Pricing snapshots, idempotency|
    +-------------------------------+
                   |
        one DB transaction
                   v
    +---------------------------------------------+
    | PostgreSQL                                  |
    | products | orders | order_items | outbox     |
    | stock_event_applications                    |
    +---------------------------------------------+
                   ^                 |
                   |                 | poll pending
                   |                 v
                   |        +---------------------+
                   +--------| Stock Worker        |
                    atomic  | idempotent consumer |
                    update  +---------------------+

    GET /products/{sku}/stock     GET /reports/daily?date=YYYY-MM-DD
```

**Decision:** one repository, one PostgreSQL database, two separate Python processes (API and worker). This is a modular event-driven monolith: independently runnable components, not distributed microservices. Polling the transactional outbox avoids requiring Kafka or RabbitMQ for a four-hour exercise.

**Delivery semantics:** outbox processing is *at least once*. Idempotent stock application yields an *effectively once* stock change, not exactly-once message delivery. `order_ref` is unique, and event IDs are unique. All balance updates and application records must commit together.

**Status semantics:** `PENDING_STOCK` means an order has been durably accepted but the inventory projection has not caught up; `STOCK_UPDATED` means the stock effect is committed. Report totals are based on accepted orders, not worker completion. Report stock is the current inventory snapshot, potentially lagging during worker pause. Document this eventual consistency.

## 3. Proposed stack and repository structure

- Python 3.10+ (documented and used by the Docker image and current host)
- FastAPI + Uvicorn
- SQLAlchemy 2.x + psycopg (or psycopg directly if simpler)
- PostgreSQL 15+; migrations via Alembic or a small deterministic SQL initializer
- pytest + HTTPX for tests
- Standard-library `argparse` or a tiny CLI for seed/demo/pause/resume workflows
- Docker Compose **optional** for PostgreSQL convenience, but native local startup instructions required

```text
mr-d-orders/
├── app/
│   ├── api/                 # orders.py, products.py, events.py
│   ├── orders/              # service.py, repository.py
│   ├── inventory/           # service.py
│   ├── outbox/              # repository.py, worker.py
│   ├── db/                  # models.py, session.py
│   ├── config.py
│   ├── reporting.py
│   ├── schemas.py
│   └── main.py
├── scripts/                 # seed.py, submit_orders.py, consume_events.py
├── migrations/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
└── SOLUTION.md
```

Adjust names only when there is a clear simplification; do not create unnecessary layers.

## 4. Data model and invariants

### `products`
- `sku` text primary key
- `name` text not null
- `price_cents` integer not null, nonnegative
- `stock` integer not null, nonnegative

### `orders`
- `id` UUID or bigint primary key
- `order_ref` text not null **UNIQUE**
- `customer_id` text not null
- `total_cents` bigint not null
- `status` text (`PENDING_STOCK`, `STOCK_UPDATED`)
- `created_at` timestamptz not null (UTC)

### `order_items`
- `id` primary key
- `order_id` foreign key
- `sku` foreign key to products
- `quantity` positive integer
- `unit_price_cents` nonnegative integer **snapshot**
- `line_total_cents` bigint

### `outbox_events`
- `event_id` UUID primary key
- `event_type` = `OrderAccepted`
- `event_version` = 1
- `aggregate_id` = order ID
- `payload` JSONB
- `created_at` timestamptz
- `processed_at` nullable timestamptz
- Optional small retry metadata only if actually needed

### `stock_event_applications`
- `event_id` primary key referencing outbox event
- `order_id` referencing orders
- `applied_at` timestamptz

### Non-negotiable invariants
- The same `order_ref` resolves to exactly one durable order and one `OrderAccepted` event.
- For the same reference and identical payload, return the existing order; document the policy for a changed payload (e.g. HTTP 409). This is a consistency guard, **not** a third demo scenario.
- Server-side pricing: client cannot provide or override prices or totals.
- Order + items + outbox event commit atomically; no external publish required.
- Worker processes each event inside a database transaction: acquire event lock, check application marker, atomically decrement stock, insert application marker, update order status and event processed timestamp, then commit.
- Prevent parallel workers from consuming one event concurrently (`FOR UPDATE SKIP LOCKED` or equivalent), and use deterministic product row locking if needed.
- Never mark an event as processed before committing the corresponding stock changes.
- The worker must recover after a crash; unprocessed durable events remain available.
- Worker pause stops **only stock processing**, not the Orders API or PostgreSQL.

## 5. Public HTTP interface

| Method | Route | Behavior |
|---|---|---|
| `POST` | `/orders` | Accept order; create order + outbox atomically; respond `202` for new pending order; duplicate identical request returns existing order without new event |
| `GET` | `/orders/{order_ref}` | Fetch order, items, total, creation time, stock status |
| `GET` | `/products/{sku}/stock` | Current stock quantity for SKU |
| `GET` | `/reports/daily?date=YYYY-MM-DD` | Accepted order count, revenue cents, units per SKU, current stock per SKU |
| `GET` | `/health` | Simple API / database health |

Example request:

```json
{
  "order_ref": "web-100045",
  "customer_id": "cust-42",
  "items": [
    {"sku": "BAN-001", "qty": 2},
    {"sku": "APL-003", "qty": 1}
  ]
}
```

Event envelope:

```json
{
  "event_id": "<uuid>",
  "event_type": "OrderAccepted",
  "event_version": 1,
  "occurred_at": "<utc iso timestamp>",
  "payload": {
    "order_id": "<id>",
    "order_ref": "web-100045",
    "customer_id": "cust-42",
    "total_cents": 597,
    "items": [
      {"sku": "BAN-001", "qty": 2, "unit_price_cents": 199},
      {"sku": "APL-003", "qty": 1, "unit_price_cents": 199}
    ]
  }
}
```

**Important:** use `price_cents`, not floating-point money. Document that daily reporting uses UTC date boundaries for order creation timestamps. Report `units_sold_per_sku` from accepted order items; report `current_stock_per_sku` from the live products table. Avoid overpromising as-of-day historical stock.

## 6. Step-by-step implementation TODO

In the phase checklists below, a checked item means its implementation or documentation is present in the repository. Live PostgreSQL execution, manual demos, and external handover items remain unchecked until their separate verification steps are completed.

### Phase 0 — Repository setup
- [x] Initialize a clean Git repository and `.gitignore` (Python cache, virtualenv, credentials).
- [x] Pick Python version and dependency management; pin a reproducible set of dependencies.
- [x] Create `.env.example` with `DATABASE_URL`, polling interval, and optional worker settings.
- [x] Create clear directories and application entrypoints.
- [x] Add minimal formatting/lint commands if low overhead (`ruff check` and `ruff format --check`).
- [x] Add a Docker Compose path for local PostgreSQL, schema/seed setup, API, and worker startup.

**Exit criteria:** [ ] Clean installation from scratch on a Unix-like machine. The available host is Windows and WSL access is denied; a clean temporary venv install also stalled before pip reported a result, so this remains unverified.

### Phase 1 — PostgreSQL schema and seed data
- [x] Build schema and reproducible migration/init command (`python -m scripts.init_db`, using PostgreSQL SQLAlchemy metadata).
- [x] Add primary keys, FKs, unique constraint on `orders.order_ref`, not-null/check constraints and useful event indexes.
- [x] Ensure timestamps are timezone-aware and stored as UTC.
- [x] Implement idempotent seed script for at least 3 products (BAN-001, APL-003, COF-005); existing stock is preserved.
- [x] Make fresh database setup documented and repeatable.

**Exit criteria:** [x] PostgreSQL 16 schema initialization succeeded and the seed command succeeded twice without changing seeded stock.

### Phase 2 — Orders capability
- [x] Define request/response models with FastAPI and Pydantic.
- [x] Implement `POST /orders` with one database transaction for order + items + outbox.
- [x] Fetch product prices from PostgreSQL and store snapshots; calculate exact integer totals.
- [x] Enforce deduplication in the **database**, not with process memory.
- [x] Handle duplicate concurrent submissions by relying on unique key and safe transaction/lookup behavior.
- [x] Return the previously created order for repeated identical `order_ref` submissions, with no extra outbox entry.
- [x] Map known API errors to 4xx responses and database/unexpected failures to sanitized 5xx responses.
- [x] Bound order quantities/line counts, reject totals outside the database range, and fail fast with actionable worker configuration errors.
- [x] Implement `GET /orders/{order_ref}` with status and item snapshot details.
- [x] Expose `/health`.

**Exit criteria:** [x] PostgreSQL integration/API checks confirmed persistence, exact totals, and one order/event for repeated identical submissions; the live API also returned 409 for a changed duplicate payload.

### Phase 3 — Transactional outbox and worker
- [x] Define a versioned `OrderAccepted` event payload.
- [x] Implement independent worker startup (`python -m app.outbox.worker`).
- [x] Poll pending outbox rows in small batches; lock safely for possible multiple workers.
- [x] Process each event within one transaction with an idempotency/application marker.
- [x] Deduct product quantities atomically; update order to `STOCK_UPDATED` and set event `processed_at`.
- [x] Handle worker shutdown/restart gracefully and avoid busy loops.
- [x] Handle poll and event failures with logs and a configured backoff while leaving uncommitted events pending.
- [x] Ensure pause/resume mechanism is simple: stopping/starting the worker process is enough.
- [x] Add observability via concise worker logs (event ID, order ref, processed/skipped, errors).

**Exit criteria:** a restarted worker drains queued events without applying a stock change twice.

### Phase 4 — Read surfaces and report (Option B only)
- [x] Implement `GET /products/{sku}/stock`.
- [x] Implement `GET /reports/daily?date=YYYY-MM-DD`.
- [x] Compute total accepted orders, summed order revenue in cents, aggregated units sold per SKU, and current stock per SKU.
- [x] Ensure report counts accepted orders once, including while worker is paused; clearly distinguish lagging stock.
- [x] Do **not** build Option A webhook/feed/consumer; the assignment says choose exactly one alternative.

**Exit criteria:** daily report results match SQL checks before and after stock catch-up.

### Phase 5 — Required demonstration scripts
- [x] `scripts/seed.py`: seed named products with fixed prices and quantities.
- [x] Implement `scripts/burst_demo.py` for a short burst including duplicate `order_ref` values, order/stock reads, and final-state checks.
- [x] Implement `scripts/outage_demo.py` and document terminal steps to stop/restart the worker, inspect pending status, and confirm catch-up.
- [x] Ensure scripts are rerunnable with fresh references, rather than failing due to prior execution.
- [x] Print before/after stock, accepted order counts, duplicate count, pending events, and final results across the demos.
- [x] Validate HTTP status/JSON responses and return a nonzero CLI result for failed setup/demo commands.
- [x] Keep the documented demo scope to the two required unhappy paths: duplicates and interruption/recovery. Runtime re-demonstration still depends on a reachable PostgreSQL/API stack.

**Exit criteria:** a reviewer can reproduce both scenarios with a few commands.

### Phase 6 — Tests and verification
- [x] Author PostgreSQL integration coverage for price snapshots, integer totals, persistence, and one outbox event.
- [x] Author PostgreSQL integration coverage for identical duplicate submissions, one event, and changed-payload conflict.
- [x] Author PostgreSQL integration coverage for paused acceptance, worker catch-up, and final stock accuracy.
- [x] Author a replay check proving an already applied event causes no further decrement.
- [x] Author API checks for order details, stock reads, daily report aggregates, and expected error mapping.
- [x] Exercise API error mapping for changed duplicates, unknown SKUs, database connectivity, and unexpected failures.
- [x] Check request-bound validation and oversized-total API error handling.
- [x] Add an importable Postman collection with API success and expected error-response assertions.
- [x] Run tests against PostgreSQL, not an SQLite substitute for transaction/locking behavior (6 passed on an isolated PostgreSQL 16 database).
- [ ] Run all documented commands on a fresh local setup; record actual commands, outputs, and any caveats in progress notes.

**Exit criteria:** tests pass, and the two required unhappy paths are visibly demonstrated.

**Verification note:** the six PostgreSQL integration tests passed on an isolated PostgreSQL 16 database. The complete documented fresh-host install and demo commands have not all been run.

### Phase 7 — Documentation and handover
- [x] Write `README.md`: prerequisites, environment, PostgreSQL creation, installation, schema initialization, seeding, API startup, worker startup, test commands, and curl examples.
- [x] Include duplicate demo and worker pause/restart steps in README.
- [x] Write `SOLUTION.md`: component boundaries, architecture diagram, schema rationale, event contract, transaction and idempotency guarantees, outbox/worker algorithm, statuses, reporting consistency, and trade-offs.
- [x] Explain why PostgreSQL polling was preferred over Kafka/RabbitMQ, and when a broker would make sense later.
- [x] Explain that at-least-once event processing plus an idempotent consumer prevents double deductions; never claim exactly-once delivery.
- [x] Explain intentionally excluded capabilities and short timebox.
- [x] Verify that no secrets or generated artifacts are committed; keep the repository concise and reviewer-friendly. Scanned tracked paths and source for environment files, generated files, and credential patterns.
- [ ] Push one well-organized GitHub repository with meaningful commits; verify clone instructions work.

**Exit criteria:** another engineer can reproduce the demonstration using README alone.

### Phase 8 — 5–10 minute narrated video
- [ ] Prepare a 5–10 minute Loom (or similar) recording with voice-over.
- [ ] 0:00–1:00 — explain the assignment, chosen scope, and architecture.
- [ ] 1:00–2:30 — show schema, Orders API, unique `order_ref`, and transactional outbox.
- [ ] 2:30–4:00 — seed and submit orders, including an intentional duplicate.
- [ ] 4:00–6:00 — stop the worker, submit orders, show persistence/pending state and unchanged stock, restart, show catch-up.
- [ ] 6:00–7:30 — show daily report endpoint and confirm expected numbers.
- [ ] 7:30–9:00 — show automated tests, idempotent worker logic, design trade-offs and future evolution.
- [ ] Ensure terminal commands and output are readable, microphone is audible, and recording length is within the requested range.
- [ ] Link the repository and video in the final submission as requested by the hiring team.

**Exit criteria:** the recording demonstrates working behavior, architecture, trade-offs, and tests without relying on assertions alone.

## 7. Reference demo dataset and expected outcomes

Use these *example* seed values (or change consistently across code/tests/docs):

| SKU | Product | Unit price | Initial stock |
|---|---|---:|---:|
| `BAN-001` | Bananas 1kg | 199 cents | 50 |
| `APL-003` | Apples 1kg | 299 cents | 40 |
| `COF-005` | Coffee | 895 cents | 25 |

Example distinct orders:

| Order ref | Items | Total |
|---|---|---:|
| `web-100045` | 2 bananas, 1 apple | 697 cents |
| `web-100046` | 1 banana, 2 apples | 797 cents |
| `web-100047` | 1 apple, 1 coffee | 1,194 cents |
| `web-100045` (repeat) | Same payload as first | No additional order or stock effect |

Expected result **after processing**: 3 unique orders; 2,688 cents revenue; units sold `BAN-001=3`, `APL-003=4`, `COF-005=1`; stock `BAN-001=47`, `APL-003=36`, `COF-005=24`. If the worker is paused, accepted orders and revenue should reflect all three distinct orders while stock remains at seeded values until recovery.

## 8. Engineering notes to include in SOLUTION.md

**Why event-driven?** Order intake remains available while stock processing is unavailable; durable events permit replay and asynchronous evolution.

**Why transactional outbox?** Saving an order and emitting an event to a separate channel in two operations creates a dual-write failure risk. Storing both in a single PostgreSQL commit avoids this for the exercise.

**Why a database uniqueness constraint?** A Python in-memory check is unsafe across retries and multiple API processes. PostgreSQL guarantees order reference uniqueness even under concurrency.

**How is stock applied once?** The worker locks a pending event and records its application alongside stock deduction and status update in the same transaction. Reprocessing checks that application marker; no second deduction occurs.

**What is eventually consistent?** The accepted order exists immediately; current stock may lag until the worker processes its outbox event. The API makes this visible through order status.

**What are the limitations?** Single database; a polling interval adds delay; no broker fanout; no stock reservations; no auth; minimal recovery controls; reporting counts accepted orders even if stock projection is delayed. A production design would define insufficient stock, cancellation, reservations, observability, retention, migrations, metrics, and scaling policies.

## 9. Codex progress log (update, never fabricate)

| Date/time UTC | Phase | Change made | Verification command/result | Remaining blocker |
|---|---|---|---|---|
| 2026-10-15 14:34 UTC | Structure and verification follow-up | Moved API handlers into `app/api/orders.py` and `app/api/products.py`, assembled them in `app/main.py`, wired order/outbox repository modules, and added the requested script entry points and migration directory. Updated the proposed structure. | `python -m compileall -q app scripts tests` passed; OpenAPI route inventory contains POST/GET orders, product stock, daily report, and health; `python -m pytest -q` => 2 passed, 5 skipped because no PostgreSQL test database/server is configured; `git diff --check` passed. Ruff is not installed. Docker is installed but the Docker Engine pipe is inaccessible. | Fresh setup, live two-process demos, Compose/Postman run, video recording, and GitHub publication still need the appropriate database/engine and handoff access. |
| 2026-10-14 08:00 UTC | Phases 0–7 (implementation) | Added Python app/schema, order API, versioned outbox worker, reports, seed/init and demo scripts, PostgreSQL integration tests, README/SOLUTION, `.gitignore`, and pinned dependencies. Selected Python 3.10+ to match available interpreter. | `python -m compileall -q app scripts tests` passed; PostgreSQL DDL compiled with SQLAlchemy's PostgreSQL dialect; app OpenAPI import listed all target routes; `git diff --check` passed. Initial run: 4 PostgreSQL checks skipped because no PostgreSQL URL/server was available. `docker info` could not connect to the Docker daemon; no `psql` installed. | PostgreSQL-backed execution/tests and manual two-process demos remain unverified. GitHub push and video are manual deliverables. |
| 2026-10-14 08:17 UTC | Error handling review | Added sanitized API exception responses, explicit CLI HTTP/JSON/database error handling, worker polling error handling/backoff, failure checks in the demos, and documented the behavior in README/SOLUTION/TODO. | `python -m compileall -q app scripts tests` passed; OpenAPI loaded; `python -m pytest -q` => 1 passed (API error mapping), 4 skipped (PostgreSQL unavailable); `python -m scripts.init_db` exited 1 with a concise database configuration error, as expected without PostgreSQL; `git diff --check` passed. | PostgreSQL behavior and full demos still need a local PostgreSQL server. |
| 2026-10-14 08:31 UTC | Phases 0–2 verification | Added pinned Ruff lint/format commands and completed the schema/order API checks using a temporary PostgreSQL 16 cluster. Confirmed seed repeatability, duplicate handling, concurrent idempotency, API reads, and API health. | `python -m ruff check app scripts tests` passed; `python -m ruff format --check app scripts tests` passed; `python -m scripts.init_db` passed; `python -m scripts.seed` ran twice and retained BAN-001=50, APL-003=40, COF-005=25; `TEST_DATABASE_URL=... python -m pytest -q` => 6 passed; live Uvicorn POST returned 202 then 200 duplicate, changed payload returned 409, GET order/stock and `/health` passed. A fresh venv dependency installation stalled and was interrupted; WSL access was denied. | Unix clean-install criterion remains unverified; Phase 0's other setup tasks and Phase 1/2 criteria are complete. |
| 2026-10-14 09:05 UTC | Error handling hardening | Added actionable configuration parse failures, request limits aligned with PostgreSQL integer storage, explicit 422 handling for BIGINT total overflow, and a guard for an impossible missing created-order result. Documented transaction rollback/error behavior and added validation/error-mapping checks. | `python -m compileall -q app scripts tests` passed; `python -m pytest -q` => 2 passed, 5 skipped (PostgreSQL unavailable); Ruff is pinned in `requirements-dev.txt` but is not installed in the current interpreter, so lint/format checks could not be rerun. | Re-run Ruff and PostgreSQL-backed suite when those tools/services are available. |
| 2026-10-14 10:53 UTC | Docker Compose and Postman | Added Dockerfile and Compose services for PostgreSQL, idempotent schema/seed setup, API, and worker. Added an ordered Postman collection covering the API’s success and expected error responses, with run instructions. Changed the DB host port mapping to dynamic assignment after the user reported host ports 5432 and 5433 conflict with other applications. | Compose config passed validation for the fixed mapping; collection JSON parsed with 11 requests and all 12 embedded scripts passed `node --check`. The user verified TCP/password authentication inside the container, while their host-side test to port 5432 failed authentication. Dynamic port mapping is in place; it still needs validation on the user's Docker host. | User needs to recreate the Compose DB port mapping, read the assigned port from `docker compose ps`, and verify pgAdmin. |

### Final verification checklist
- [x] Repo includes source, `README.md`, `SOLUTION.md` and this updated `TODO.md`.
- [ ] API and worker run as independent processes on a local PostgreSQL database.
- [ ] Docker Compose stack starts successfully and the Postman collection passes against it (Compose config is valid; Docker engine access is denied in this environment).
- [x] Exactly one accepted order and one outbox event for a repeated `order_ref` (PostgreSQL concurrency test and live API duplicate check).
- [x] Price snapshots and totals are computed server-side and remain stable (PostgreSQL integration check).
- [x] Paused worker does not prevent order intake (PostgreSQL integration check).
- [x] Resumed worker catches up and reduces each order's stock exactly once (PostgreSQL integration/replay checks).
- [x] Daily report returns expected totals and current stock (PostgreSQL integration check).
- [ ] Tests pass on PostgreSQL and runnable commands match README.
- [ ] Video demo is recorded and GitHub link is ready to share.

---

## One-shot instruction to paste into Codex

> Read `TODO.md` in full. Build this Mr D Orders & Stock assignment using the proposed lightweight PostgreSQL-backed event-driven architecture. Follow all phases in order, update checklist items only after implementation and verification, and maintain the progress log. Implement a separately runnable FastAPI Orders API and idempotent polling Stock Worker, plus **Option B daily reporting only**. Include deterministic seed/burst scripts, demonstrate exactly the two requested unhappy paths (duplicate orders and worker interruption/recovery), run PostgreSQL-backed tests, and write honest `README.md` and `SOLUTION.md`. Avoid overengineering or adding external brokers. Finish with a concise summary of verified results and anything requiring manual action (GitHub push/video recording).
