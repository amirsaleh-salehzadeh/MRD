# Five-minute recording run sheet

Use a fresh database if quoting the initial stock. `python -m scripts.seed` is insert-only and will not reset inventory. The actual contract is in `API_CONTRACT.md`; the full command sequence is in `TEST_WALKTHROUGH.md`.

## Prepare

```bash
docker compose up --build -d
docker compose ps
```

Confirm `db`, `setup`, `api`, and `worker` are healthy/completed. Open Postman collection `postman/Mr-D-Orders.postman_collection.json` for supplementary API checks. For the recording, keep to one happy path and exactly these two unhappy paths: duplicate retry and temporary worker outage.

## 0:00–1:20 — Architecture

Introduce the FastAPI/PostgreSQL order flow and Option B daily report. Show `SOLUTION.md`: order/items/outbox transaction, worker, and order statuses. Mention that this repo has no public `/events` endpoint.

## 1:20–2:35 — Happy path

Show fresh seed stock: BAN-001 50, APL-003 40, COF-005 25. Submit an order for 2 BAN-001. Expected total 398 cents; poll the order to `STOCK_UPDATED`; BAN-001 becomes 48.

## 2:35–3:25 — Unhappy path 1: duplicate

Repeat the identical order body with the same reference. Show HTTP 200, `duplicate: true`, and the same `order_id`. Stock remains 48. Do not add another duplicate variation to the recorded run.

## 3:25–4:35 — Unhappy path 2: worker outage

Stop only the stock worker (`docker compose stop worker`). Record current BAN-001 stock S. Submit two new order references with one BAN-001 each. Show both accepted/pending and stock still S. Resume with `docker compose start worker`; poll both orders and show stock S-2.

## 4:35–5:00 — Report and close

Call `/reports/daily?date=<UTC-date>` and show accepted count, revenue, units, and current stock. Explain that report counts accepted orders while stock can lag during worker downtime. Point to `AUDIT_RESULTS.md` for actual verification results; do not claim skipped PostgreSQL or unavailable Docker checks passed.

## Cleanup

```bash
docker compose down
```

This preserves the database volume. Use `docker compose down -v` only when intentionally deleting local database data.
