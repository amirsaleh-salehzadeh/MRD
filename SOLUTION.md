# Solution notes

## Components

- **Orders API (`app.main`)** accepts a request, reads authoritative product prices, and commits its order, snapshot line items, and `OrderAccepted` JSONB event in one PostgreSQL transaction.
- **PostgreSQL** is both the system of record and the durable queue. A unique constraint on `orders.order_ref` is the idempotency boundary.
- **Stock Worker (`app.worker`)** runs independently and polls pending events. Each event is locked with `FOR UPDATE SKIP LOCKED`; stock updates, the event application marker, order status, and `processed_at` commit in the same transaction.
- **Read/report routes** expose order state, current stock, and a UTC-day accepted-order report.

```text
Client -> Orders API -> PostgreSQL (orders + items + outbox)
                              ^                 |
                              |                 v
                       inventory tables <- Stock Worker
Client -> read endpoints / daily report <- PostgreSQL
```

## Schema and invariants

`products` holds integer cent prices and nonnegative inventory. `orders.order_ref` is unique. `order_items` keeps the SKU, quantity, unit price snapshot, and line total. `outbox_events` holds a versioned event envelope as JSONB, including its event ID, type, version, UTC occurrence time, and order payload. `stock_event_applications.event_id` is the consumer idempotency marker.

The schema is created deterministically by SQLAlchemy metadata through `python -m scripts.init_db`. It uses PostgreSQL UUID, JSONB, constraints, foreign keys, and timezone-aware timestamps. Seeding is insert-only on SKU so rerunning it does not replenish or overwrite stock.

The API calculates totals from product prices in integer cents. It never accepts prices from the client. A repeat with identical reference/customer/item lines returns the existing order and emits no event. Reusing a reference with changed customer or item lines returns 409. The database insert uses `ON CONFLICT DO NOTHING` against the unique reference so concurrent submissions converge on the same durable row.

## Outbox and worker guarantees

The API has no dual-write to a separate broker: it stores the order and event in one commit. Event delivery is at least once. The worker locks an event row and checks its application marker before making any stock change. Conditional atomic decrements prevent negative stock. The marker, stock changes, status update, and processed timestamp share a transaction, so a crash rolls all of them back together. Replaying an applied event is a no-op.

Insufficient stock causes the transaction to roll back and leaves the event pending, with a concise worker error log. The sample data assumes enough stock; choosing a reservation, rejection, or oversell policy is intentionally outside this exercise.

Stopping the worker stops only stock processing. The API and PostgreSQL remain available, and accepted orders build up durably. Starting the worker again drains the pending events. No broker was added because a PostgreSQL poller keeps this four-hour demo small; a broker would be useful for broader fan-out, independent consumers, or throughput beyond the database's comfortable polling load.

## Status and reporting consistency

`PENDING_STOCK` means the order and event are committed while the stock projection awaits processing. `STOCK_UPDATED` means the stock effect was committed. The daily report uses UTC order-creation day boundaries. It counts accepted orders and their item units regardless of worker state, and reports current stock from `products`; it is not historical as-of-day inventory. Thus stock may lag during a worker pause.

## Error handling

The API maps expected request failures to stable HTTP responses: validation/unknown SKU to 422, changed duplicate references to 409, missing resources to 404, and database connectivity failures to 503. Database and unexpected server errors return generic responses; server logs retain the diagnostic details. The worker catches polling and per-event failures, logs identifiers, leaves uncommitted events pending, and waits for the polling interval before retrying. CLI scripts check HTTP status and JSON shape, report API/database failures, and exit nonzero instead of presenting failed responses as demo results.

Request bounds keep persisted values representable: each order has 1–100 item lines, each quantity fits PostgreSQL `INTEGER`, and a total larger than PostgreSQL `BIGINT` is rejected with HTTP 422 inside the transaction so partial order, item, and outbox writes are rolled back. Invalid worker configuration fails immediately with an actionable setting-specific message.

Domain/service functions let unexpected persistence and data errors propagate so their transaction boundaries can roll back. The API, worker loop, and CLI entry points handle those failures where they can choose the correct client response, retry/backoff behavior, or process exit status.

## Scope limits

This is a single-database local demo with polling delay and basic logging. It has no authentication, payments, reservations, cancellation/refunds, broker fan-out, retry framework, retention policy, metrics, or sophisticated stock-shortage handling. Production work would define those policies, plus migration/versioning operations, monitoring, and scaling limits.
