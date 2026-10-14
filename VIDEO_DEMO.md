# Video demo recording guide

This guide is a ready-to-record voice-over plan for the requested 5–10 minute demo. The recording itself should be made with Loom or another screen recorder while the local stack is running.

## Before recording

For a clean demo database, start Docker Desktop and reset the local volume before starting the stack:

```bash
docker compose down -v
docker compose up --build -d
docker compose ps
```

The `down -v` command deletes the local demo database volume. Use it only when you are happy to reset demo data.
Open `http://localhost:8000/docs` and keep a terminal available.

## Suggested 7-minute walkthrough

### 0:00–0:45 — What the project demonstrates

“This is a small Python and PostgreSQL order intake and stock update service. The API accepts orders and calculates totals from database prices. It stores accepted orders durably, even while the independent stock worker is paused. I chose the minimal daily report as the external surface.”

### 0:45–2:00 — Architecture and storage

Show `SOLUTION.md`, then `app/models.py` and `app/orders.py`.

“PostgreSQL stores products, orders, item price snapshots, and an outbox event. The order and its `OrderAccepted` event commit in one transaction, so an accepted order cannot be separated from its stock update request. The unique order reference is the idempotency boundary.”

Point out that the event payload carries quantities and captured prices, while the worker only needs the quantities to update stock.

### 2:00–3:30 — Duplicate submission demonstration

Run:

```bash
python -m scripts.burst_demo
```

“The burst submits three distinct orders and then repeats the first order reference with the same payload. The API returns the existing order and marks the response as a duplicate. Only one order and one outbox event count for that reference, so stock is reduced once.”

Show the printed duplicate result, final order statuses, and stock changes. In Swagger, optionally open `GET /orders/{order_ref}` for one printed reference.

### 3:30–5:30 — Worker interruption and catch-up

Stop the worker terminal with Ctrl+C. Leave the API and database running. Then run:

```bash
python -m scripts.outage_demo
```

“The stock worker is paused, but order intake still commits to PostgreSQL. The orders report `PENDING_STOCK`; inventory has not changed yet. The outbox is the durable backlog.”

Restart the worker:

```bash
python -m app.worker
```

Query the order references printed by the outage script:

```bash
curl http://localhost:8000/orders/<printed-order-reference>
```

“After recovery the worker drains those events. The order status becomes `STOCK_UPDATED` and the stock endpoint reflects the decrements.”

### 5:30–6:30 — Read API and daily report

Show the order details, a stock route such as `/products/BAN-001/stock`, and `/reports/daily?date=<current-UTC-date>`.

“The report returns accepted order count, revenue in cents, units by SKU, and current stock by SKU. During a worker pause it explicitly reflects the fact that stock can lag.”

### 6:30–7:15 — Trade-offs and close

“The outbox and worker use PostgreSQL instead of adding a broker, which keeps this local exercise small and makes recovery durable. Delivery is at least once, while an application marker and a single transaction make stock application idempotent. The demo assumes enough stock; a production system would need a defined shortage policy, migrations, monitoring, and operational retry controls.”

## Recording checklist

- Keep the API and worker logs readable and avoid showing `.env` secrets.
- Show the duplicate response and the paused and recovered statuses clearly.
- Keep the narration focused on the two demonstrations, the transaction boundary, and the PostgreSQL outbox trade-off.
- Aim for 6–8 minutes; the timings above can be shortened or expanded as needed.
