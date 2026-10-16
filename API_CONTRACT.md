# API contract

Business routes use `http://localhost:8000/api/v1`. `/health`, `/ready`, and `/reports/daily` are operational/reporting routes and remain unversioned. Each business operation has one canonical route; legacy unversioned order and product aliases have been removed.

## Orders

### `POST /api/v1/orders`

Request (1–100 item lines, positive integer quantities):

```json
{"order_ref":"web-100045","customer_id":"cust-42","items":[{"sku":"BAN-001","qty":2}]}
```

New order returns **202**; same reference and same customer/items returns **200** with same ID and `duplicate: true`. A changed payload for an existing reference returns **409**. Unknown SKU or invalid request returns **422**.

```json
{"order_id":"<uuid>","order_ref":"web-100045","total_cents":398,"status":"PENDING_STOCK","duplicate":false}
```

### `GET /api/v1/orders/{order_id}`

Looks up by the UUID order ID and returns `id`, `order_ref`, `customer_id`, `total_cents`, `status`, `created_at`, and `items` containing SKU, quantity (`qty`), and price snapshots. Missing order: **404**. `PENDING_STOCK` means accepted while awaiting stock projection; `STOCK_UPDATED` means the worker committed the stock effect.

## Products

- `GET /api/v1/products`: array of `{sku,name,price_cents,stock}`, ordered by SKU.
- `GET /api/v1/products/{sku}`: one product in the same shape; unknown SKU returns **404**.
- `GET /api/v1/products/{sku}/stock`: `{sku,stock}`; unknown SKU returns **404**.
- `POST /api/v1/products`: creates a product using `{sku,name,price_cents,stock}`, returns **201**. Invalid fields return **422**; existing SKU returns **409** and is never overwritten.

These local-demo endpoints have no authentication. Product creation is an operator/demo capability; production exposure would need authorization.

## Events

- `GET /api/v1/events?limit=50&cursor=<event_uuid>` returns `{items:[...],next_cursor:<uuid|null>}` ordered by creation time and event ID. `limit` is 1–100. Omit cursor for the first page; pass `next_cursor` to continue. Events remain visible after stock processing; `processed_at` is not used as a feed receipt.
- `GET /api/v1/events/{event_id}` returns one event or **404**.

Each event contains `event_id`, `event_type`, `event_version`, `aggregate_id`, `payload` (the persisted versioned envelope), and `created_at`. Consumers should deduplicate by `event_id`. Delivery is repeatable: retain the cursor and deduplicate because a client may retry a page. An unknown cursor returns **404**.

## Health and report

- `GET /health`: liveness response `{"status":"ok"}`; does not query PostgreSQL.
- `GET /ready`: database readiness `{"status":"ready"}` or **503** when PostgreSQL is unavailable. Compose uses this for API health.
- `GET /reports/daily?date=YYYY-MM-DD`: existing UTC-day accepted order count, revenue, units by SKU, and current stock. Stock may lag while the worker is stopped.

Database connection failures return generic **503** JSON; unexpected database/server failures return generic **500** JSON. Diagnostics are logged server-side.
