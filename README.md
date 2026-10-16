# Mr D Orders & Stock

A Python and PostgreSQL service that accepts orders and updates stock with a separate worker.

## Why event-driven processing

The API writes an order and its `OrderAccepted` outbox event in the same database transaction. This ensures that an accepted order always has a durable stock-update request. A separate worker processes the event, so the API can keep accepting orders while the worker is stopped; pending events are handled when it returns. The worker records each applied event to prevent retries from changing stock twice.

PostgreSQL already stores the order data, so using it as the durable event queue keeps this project simple without adding a message broker. The trade-off is that stock can temporarily lag behind accepted orders while events wait for the worker.

See [SOLUTION.md](SOLUTION.md) for the processing flow and reliability details.

## Run the application

Start the stack with Docker Desktop running:

```powershell
docker compose up --build -d
docker compose ps
```

The API is at <http://localhost:8000>; interactive documentation is at <http://localhost:8000/docs>. Compose publishes PostgreSQL on host port `64670`; containers connect to it as `db:5432`.

To stop the stack and preserve database data:

```powershell
docker compose down
```

## Run pytest in Docker

The tests need a separate PostgreSQL database. Create it once; if it already exists, skip this command:

```powershell
docker compose up -d db
docker compose exec db psql -U mrd -d postgres -c "CREATE DATABASE mrd_orders_test OWNER mrd;"
```

Build the current API image, then run the tests with the project’s `tests` folder mounted into a temporary container:

```powershell
docker compose build api
docker compose run --rm --no-deps `
  -v "${PWD}/tests:/app/tests" `
  -e TEST_DATABASE_URL="postgresql+psycopg2://mrd:mrd-local@db:5432/mrd_orders_test" `
  api sh -c "python -m pytest -q -rs /app/tests"
```

Use `db:5432` in this container command. Use `localhost:64670` only when running pytest directly on the host. Test data remains in the dedicated test database.

## Try the API

Business routes use `/api/v1`. For example, create an order with `POST /api/v1/orders`, look it up with `GET /api/v1/orders/{order_id}`, and check stock with `GET /api/v1/products/{sku}/stock`. The daily report is at `/reports/daily?date=YYYY-MM-DD`.

Import [`postman/Mr-D-Orders.postman_collection.json`](postman/Mr-D-Orders.postman_collection.json) into Postman. Run the **Automated API checks** folder in order with the stack running. Full routes and request/response details are in [API_CONTRACT.md](API_CONTRACT.md).

## Demonstrate worker recovery

With the API and worker running, run the burst demo to show duplicate-order handling:

```powershell
docker compose exec api python -m scripts.burst_demo
```

To demonstrate recovery, stop the worker, submit orders while it is paused, then start it again:

```powershell
docker compose stop worker
docker compose exec api python -m scripts.outage_demo
docker compose start worker
```

The Postman collection includes separate pause and recovery folders for this manual scenario. Stop the worker before running the pause folder, then start it and run the recovery folder. The queued order should move from `PENDING_STOCK` to `STOCK_UPDATED` after the worker processes its event.
