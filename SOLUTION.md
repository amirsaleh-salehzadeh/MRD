# Solution Overview

## Design choice: transactional outbox

Accepting an order and changing stock are separate jobs. The API needs to respond quickly, while stock processing can take place independently and may be unavailable temporarily. The system uses an event-driven flow with a PostgreSQL outbox: the API writes the order and its `OrderAccepted` event in the **same database transaction**, then a worker processes the event.

This avoids a dual-write failure where an order commits but its stock-update instruction is lost. If the worker is stopped, accepted orders remain durable and stock events wait in PostgreSQL. When the worker resumes, it processes the backlog. PostgreSQL already holds the order data, so it also serves as the queue without adding a separate broker.

The trade-off is eventual consistency: an accepted order can remain `PENDING_STOCK` until the worker processes its event. Stock and order status then catch up.

## Processing flow

1. The API validates the request and reads product prices from PostgreSQL.
2. In one transaction, it saves the order, item price snapshots, and versioned `OrderAccepted` outbox event.
3. The worker polls for unprocessed outbox events, selecting them in creation-time order.
4. For each event, it locks the row with `FOR UPDATE SKIP LOCKED`, calculates quantities, and decrements stock only when enough stock is available.
5. In the same transaction, it records the event application, sets the order to `STOCK_UPDATED`, and marks the event as processed.

If processing fails, the transaction rolls back. The event stays pending and the worker retries it on a later poll. If the worker receives `SIGINT` or `SIGTERM`, it stops polling and exits; unprocessed events remain in the database for the next run.

## Components

- **Orders API (`app/api/orders.py`, `app/orders/service.py`)** accepts orders, calculates totals using database prices, handles duplicate references, and returns order details.
- **PostgreSQL (`app/db/models.py`)** stores products, orders, item snapshots, outbox events, and event application records.
- **Outbox worker (`app/outbox/worker.py`)** polls pending events and applies stock changes through `app/inventory/service.py`.
- **Read APIs (`app/api/products.py`, `app/api/events.py`, `app/main.py`)** expose product and stock details, event records, health and readiness checks, and the daily report.

```text
Client -> Orders API -> PostgreSQL (order + items + outbox event)
                                   |
                                   v
                             Stock worker
                                   |
                                   v
                       PostgreSQL (stock + application record)
```

## Data and API rules

- `products` stores current price in cents and current stock. Database constraints prevent negative stock and prices.
- `orders.order_ref` is unique and is the idempotency key. An identical retry returns the existing order without emitting another event; a different payload using the same reference returns HTTP 409.
- `order_items` stores the quantity, unit price, and line total captured at order time. Client-submitted prices are not trusted.
- `outbox_events` stores a versioned event envelope. `stock_event_applications` records which event the inventory worker has applied.
- Business routes have one canonical versioned path under `/api/v1`. The event feed is paginated and remains readable after the worker processes an event.
- `/health` checks that the API process responds; `/ready` checks PostgreSQL connectivity. `/reports/daily` summarizes accepted orders by UTC creation date and shows current stock, which may lag during a worker pause.

## Guarantees and limits

The outbox event is persisted atomically with the order. Worker stock updates, the application record, order status, and event acknowledgement commit together. If the worker sees an already applied event, it skips the stock change. Conditional stock updates prevent inventory from becoming negative.

An insufficient-stock event remains pending and is logged; this demo does not define whether a real order should be rejected, reserved, or allowed to oversell. The system also omits authentication, payments, cancellation, schema migrations, metrics, and advanced retry controls. Those policies and operational features would be needed before production use.
