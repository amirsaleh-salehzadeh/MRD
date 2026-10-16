# Reproducible test walkthrough

The exact API, status codes and fields are in [API_CONTRACT.md](API_CONTRACT.md). The deterministic seed is BAN-001 (199 cents, 50 units), APL-003 (299 cents, 40 units), COF-005 (895 cents, 25 units). Seeding is insert-only and does not reset existing inventory.

## Start locally

Use the README Compose route or provision PostgreSQL and run:

```bash
python -m scripts.init_db
python -m scripts.seed
uvicorn app.main:app --reload
python -m app.outbox.worker
```

Run API and worker in separate terminals. With Compose, pause/resume only the worker using `docker compose stop worker` and `docker compose start worker`.

## Happy path

Record BAN-001 stock (`S`, 50 on a fresh seeded DB). Submit a unique order with 2 BAN-001 and 1 APL-003 to `POST /api/v1/orders`. Expected total is 697 cents, status is initially `PENDING_STOCK`, and item snapshots are 199 and 299 cents. Use the returned `order_id` with `GET /api/v1/orders/{order_id}` until status becomes `STOCK_UPDATED`; stock becomes BAN-001 `S-2` and APL-003 `38` on a fresh DB.

## Required unhappy path 1: identical duplicate

Repeat exactly the same body and order reference. Expect HTTP 200, the same `order_id`, `duplicate: true`; the database has one order and one outbox event for that order. Stock remains at its already-updated value.

## Required unhappy path 2: worker outage and recovery

Use fresh references. Record the current BAN-001 baseline `S`, then stop the worker **before** submitting. Submit two orders for that SKU: quantities 3 and 4. Both are accepted (202), both remain `PENDING_STOCK`, and stock remains `S`. Resume the worker and poll until both orders are `STOCK_UPDATED`; stock becomes `S-7`.

## SQL evidence

```sql
SELECT order_ref, id, total_cents, status FROM orders ORDER BY created_at DESC LIMIT 10;
SELECT order_id, sku, quantity, unit_price_cents, line_total_cents FROM order_items ORDER BY id DESC LIMIT 10;
SELECT event_id, event_type, processed_at FROM outbox_events ORDER BY created_at DESC LIMIT 10;
SELECT event_id, order_id, applied_at FROM stock_event_applications ORDER BY applied_at DESC LIMIT 10;
SELECT sku, stock FROM products WHERE sku IN ('BAN-001', 'APL-003');
```

Use only the duplicate and outage scenarios as the two recorded unhappy paths. The versioned accepted-order event feed is available at `/api/v1/events`; the daily report remains available at `/reports/daily`.
