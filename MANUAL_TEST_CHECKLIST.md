# Five-Minute Postman Video Run Sheet

Use this timed checklist while recording your voice-over. It is designed for a concise five-minute walkthrough of the project and its two demonstrations: duplicate submission and stock catch-up after a worker pause.

## Prepare before recording

- [ ] Start Docker Desktop and run the stack:

  ```bash
  docker compose up --build -d
  docker compose ps
  ```

- [ ] Confirm `db`, `api`, and `worker` are running and `setup` completed.
- [ ] Import `postman/Mr-D-Orders.postman_collection.json` into Postman.
- [ ] Confirm the collection's `baseUrl` variable is `http://localhost:8000`.
- [ ] Open a terminal for the worker. Keep it visible or easy to switch to during the outage section.
- [ ] Have Postman and the project source (`app/orders/service.py`, `app/outbox/worker.py`, `app/db/models.py`, and `SOLUTION.md`) ready to show.
- [ ] Start recording only once the stack and Postman are ready. Keep the database running throughout.

## Recording checklist and narration

### 0:00–0:35 — Introduce the project

- [ ] Show the Postman collection and briefly show the project folder.
- [ ] Say: “This is a Python and PostgreSQL order service. It accepts orders, snapshots prices, and updates stock with a separate worker. I’ll show duplicate protection and how stock catches up after a brief worker pause.”

### 0:35–1:15 — Explain the design

- [ ] Briefly show `app/orders/service.py`, `app/db/models.py`, and `app/outbox/worker.py` (or show the architecture in `SOLUTION.md`).
- [ ] Say: “The API stores the order, item price snapshots, and an OrderAccepted outbox event in one PostgreSQL transaction. A unique order reference prevents a second order. The worker reads pending events from PostgreSQL and updates stock, so accepted orders remain durable while the worker is stopped.”

### 1:15–2:25 — Run the Postman collection for duplicates

- [ ] In Postman, run the **Mr D Orders API** collection in its listed order.
- [ ] Show the passing results for **Create order**, **Repeat identical order (idempotency)**, and **Changed duplicate payload (409)**.
- [ ] Say: “The first request creates an order and calculates 498 cents from the seeded prices. Repeating the same reference and payload returns the same order ID as a duplicate. Changing the payload for that reference returns a conflict, so it cannot silently count as a different order.”
- [ ] Briefly show **Get order** and **Get BAN-001 stock** results. Mention that the worker processes stock asynchronously.

### 2:25–3:45 — Show the worker pause in Postman

- [ ] In the worker terminal, press Ctrl+C to stop the worker. Leave the API and database running.
- [ ] In Postman, send **Get BAN-001 stock** and note its value.
- [ ] Send **Create order**. The collection generates a fresh reference; confirm HTTP 202 and `PENDING_STOCK`.
- [ ] Send **Get order** and confirm it is still `PENDING_STOCK`.
- [ ] Send **Get BAN-001 stock** again and show that it has not yet changed for this order.
- [ ] Say: “The stock worker is paused, but the API still accepts the order. PostgreSQL keeps the event pending, so the stock projection is temporarily behind.”

### 3:45–4:25 — Resume and show catch-up

- [ ] Restart the worker in the terminal:

  ```bash
  python -m app.outbox.worker
  ```

- [ ] In Postman, send **Get order** again. If it is still pending, wait a moment and resend until it shows `STOCK_UPDATED`.
- [ ] Send **Get BAN-001 stock** and show the updated value.
- [ ] Say: “After restart, the worker processes the stored event. The order status and stock now reflect the completed update.”

### 4:25–5:00 — Show report and close

- [ ] Send the collection's **Daily report** request. Show `accepted_orders`, `revenue_cents`, `units_sold_per_sku`, and `current_stock_per_sku`.
- [ ] Say: “The report summarizes accepted orders and current stock for a UTC day. I chose this report as the external surface. The trade-off is that PostgreSQL polling keeps the demo simple, while stock can lag briefly if the worker is paused.”
- [ ] End the recording at about five minutes.

## Postman collection requests

The full collection also checks health, stock lookup, reporting, unknown SKU, invalid quantity, and missing-resource responses. These checks run automatically with the collection. If time is tight, keep the video focused on the three duplicate requests and the pause/recovery sequence above.

The collection creates a fresh order reference for each run and uses the current UTC date for its report request.

## After recording

- [ ] Restart the worker if it is still stopped.
- [ ] Stop the stack while preserving database data:

  ```bash
  docker compose down
  ```

- [ ] To delete the local database volume and demo data as well, run `docker compose down -v` instead.
