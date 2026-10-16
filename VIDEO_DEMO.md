# Video demo scenario — 5 to 8 minutes

Use this as a spoken walkthrough. The target is about 7 minutes. The live API demonstrations require the API and PostgreSQL to be running. If Docker Engine pipe access is still denied, do not present the live demo as completed: use the recorded audit evidence for the runtime limitation and demonstrate the code and expected flow instead, or run against a separately available PostgreSQL instance.

## Before recording

- Keep `README.md`, `SOLUTION.md`, `AUDIT_RESULTS.md`, and `http://localhost:8000/docs` ready to show.
- If the stack is available, start it with `docker compose up --build -d`, then confirm services with `docker compose ps` and open `/docs`.
- Keep `.env`, passwords, and other secrets off screen.
- If using a fresh database, the sample stock is BAN-001: 50, APL-003: 40, COF-005: 25. Seeding is insert-only and does not reset existing stock.

## 0:00–0:40 — Introduce the project

**Show:** README and the project tree.

**Say:** “This project is a small Python and PostgreSQL order service. It accepts orders, calculates prices from the product database, saves a snapshot of those prices, and updates inventory through a separate background worker. I’ll show how the service handles a repeated request and what happens when the worker is temporarily unavailable.”

## 0:40–1:35 — Explain the design

**Show:** `SOLUTION.md`, then the order service and database models.

**Say:** “When an order is accepted, the order, its item and price snapshots, and an `OrderAccepted` outbox event are committed together. That means the request to update stock is stored durably with the order. The worker reads those events and applies stock changes. An order can be `PENDING_STOCK` while the event is waiting, then becomes `STOCK_UPDATED` after the worker succeeds.”

## 1:35–2:10 — Show the running service

**Show:** `docker compose ps`, then Swagger at `/docs`; optionally point out `db`, `setup`, `api`, and `worker` in `docker-compose.yml`.

**Say:** “Compose starts PostgreSQL, initializes the schema and sample products, and then runs the API and worker. The API exposes the order, product, stock, event, and daily report routes. Health and readiness are separate: health reports that the API process is alive, while readiness checks the database.”

If Compose cannot start, say: “I could not complete the live startup in this environment because access to the Docker Engine named pipe was denied. The Compose configuration is present, but I won’t claim the live runtime flow passed. I’ll show the implementation and the recorded verification status.” Then show the relevant entry in `AUDIT_RESULTS.md` and continue with the design sections below.

## 2:10–3:10 — Demonstrate an order and identical retry

**Show:** Submit an order through `/docs` or the supplied Postman collection. Use a new reference and two units of BAN-001. Show the response, then repeat the exact same request with the same reference. Show order details and stock if the worker is running.

**Say:** “The first request is accepted, and the order total is calculated from the database price. Repeating the same reference with the same customer and item lines returns the existing order with `duplicate: true`; it does not create a second order or apply stock twice. A changed payload for that same reference is rejected with HTTP 409.”

For a fresh sample database, two BAN-001 units cost 398 cents and stock goes from 50 to 48 after processing. If the database has been used before, describe the actual values displayed rather than quoting the fresh-seed numbers.

## 3:10–5:25 — Demonstrate worker pause and recovery

**Show:** Stop the worker process with Ctrl+C, leaving the API and database running. Record the current BAN-001 stock. Submit two orders using different references, one BAN-001 unit each. Show their accepted responses and pending statuses, then check stock is unchanged. Restart the worker with `python -m app.outbox.worker`, poll the two orders, and show their final statuses and stock.

**Say:** “The worker is paused, but the API can still accept and store orders. Both orders remain `PENDING_STOCK`, and stock stays at its previous value because the worker has not applied the outbox events. Once I restart the worker, it catches up. The orders move to `STOCK_UPDATED`, and stock decreases by two units in total.”

## 5:25–6:10 — Show the daily report

**Show:** `/reports/daily?date=<UTC-date>` and a product stock route.

**Say:** “The daily report summarizes accepted orders, revenue in cents, units by SKU, and current stock. Accepted orders are counted even during a worker pause, so the report can show current inventory lagging behind accepted demand.”

## 6:10–7:00 — Close with verification and trade-offs

**Show:** `AUDIT_RESULTS.md`, then the relevant section of `SOLUTION.md`.

**Say:** “The outbox uses PostgreSQL rather than a separate message broker, which keeps this exercise small while preserving events across a worker interruption. Delivery is at least once, and the application marker and transaction make stock application idempotent. The recorded checks show what was actually verified: PostgreSQL-dependent checks were skipped when PostgreSQL was unavailable, and Docker Engine access prevented a live Compose startup. A production version would need a defined insufficient-stock policy, migrations, monitoring, and operational retry controls.”

## Recording guardrails

- Aim for 6–7 minutes; shorten the architecture explanation if you need to stay under 8.
- Only describe live API behavior as observed if you actually ran it during the recording.
- Keep the two demonstrations focused: identical retry, then worker interruption and recovery.
- If Docker is still blocked, clearly label the video as a code and evidence walkthrough rather than a successful live-stack demo.
