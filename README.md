# Mr D Orders & Stock Core Flow

A small PostgreSQL-backed commerce demo: the Orders API stores orders and immutable price snapshots together with an `OrderAccepted` outbox event. A separate polling worker applies stock changes. Daily reporting counts accepted orders and shows the live stock projection.

## Requirements

- Python 3.10 or newer
- PostgreSQL 15 or newer
- Windows, Linux, or macOS; PostgreSQL can be local or in Docker

The implementation uses Python 3.10 syntax so it can run on the provided Python 3.10 environment. PostgreSQL is required; SQLite is not supported for application or concurrency checks.

## Run the full stack with Docker Compose

With Docker Desktop (or Docker Engine with the Compose plugin) running:

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f api worker
```

Compose starts PostgreSQL, waits for its health check, initializes the schema and inserts any missing sample products, then starts the API and worker. The API listens at `http://localhost:8000` and its OpenAPI page is at `http://localhost:8000/docs`. The sample database credentials in `docker-compose.yml` are for local development only.

Stop the stack and preserve database data with `docker compose down`. To delete the Compose database volume and all its data, run `docker compose down -v`.

Compose publishes PostgreSQL on a dynamically assigned host port to avoid conflicts with other local applications. Containers still connect to the database on its internal port `5432`. Run `docker compose ps` to see the assigned host port (for example, `0.0.0.0:49153->5432/tcp`).

For pgAdmin running on the host, register a server with host `127.0.0.1`, the assigned host port shown by `docker compose ps`, maintenance database `mrd_orders`, username `mrd`, and password `mrd-local`. If pgAdmin is itself in the Compose network, use host `db` and port `5432`.

### Run the Postman checks

Import [`postman/Mr-D-Orders.postman_collection.json`](postman/Mr-D-Orders.postman_collection.json) into Postman, start the Compose stack, select the collection, and click **Run**. Keep the requests in their listed order. The collection uses `http://localhost:8000` by default and creates a unique order reference when it runs. Its assertions cover health, order creation, identical retry/idempotency, changed-payload conflict, order details, stock, daily reporting, unknown SKU and invalid-input errors, and missing-resource errors. The worker may update stock between requests, so the stock assertion checks the valid range instead of assuming a timing-specific value.

To change the API address, edit the collection variable `baseUrl` before running it. These are HTTP-level Postman checks; PostgreSQL concurrency and worker replay behavior remain covered by `pytest`.

## Set up PostgreSQL

Create a database named `mrd_orders` and a user with permission to create tables. For example, from `psql` as a database administrator:

```sql
CREATE USER mrd WITH PASSWORD 'mrd-local';
CREATE DATABASE mrd_orders OWNER mrd;
```

Copy `.env.example` to `.env` and set `DATABASE_URL`, for example:

```text
DATABASE_URL=postgresql+psycopg2://mrd:mrd-local@localhost:5432/mrd_orders
POLL_INTERVAL_SECONDS=1.0
WORKER_BATCH_SIZE=25
```

## Install and initialize

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m scripts.init_db
python -m scripts.seed
```

The schema initializer is safe to repeat. Seeding inserts the three sample products only when each SKU is absent; it does not reset existing stock.

Run the lightweight checks before handing off changes:

```bash
python -m ruff check app scripts tests
python -m ruff format --check app scripts tests
python -m pytest -q
```

## Run the API and worker

Start each process in its own terminal with the virtual environment activated:

```bash
uvicorn app.main:app --reload
```

```bash
python -m app.worker
```

The API is at `http://127.0.0.1:8000`; interactive API docs are at `/docs`.

## Try the API

```bash
curl -X POST http://127.0.0.1:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"order_ref":"web-100045","customer_id":"cust-42","items":[{"sku":"BAN-001","qty":2},{"sku":"APL-003","qty":1}]}'
curl http://127.0.0.1:8000/orders/web-100045
curl http://127.0.0.1:8000/products/BAN-001/stock
curl 'http://127.0.0.1:8000/reports/daily?date=2026-10-14'
curl http://127.0.0.1:8000/health
```

Prices and totals come from the database. Repeating the same `order_ref` with the same customer and item lines returns the existing order with `duplicate: true`; a changed payload for that reference returns HTTP 409. The API accepts a new order with HTTP 202; an identical duplicate returns HTTP 200. Unknown SKUs and invalid request shapes are rejected for basic operability.

### Errors and recovery

- Invalid request data or an unknown SKU returns HTTP 422; a changed duplicate payload returns HTTP 409; missing orders/products return HTTP 404.
- Database connection failures return HTTP 503. Other database failures and unexpected API errors return a generic HTTP 500 response; details are written to the server log rather than returned to the caller.
- Invalid worker settings fail at startup with the setting name and expected type/range. Order requests require 1–100 lines and quantities that fit the database integer column; totals beyond PostgreSQL `BIGINT` return HTTP 422 and the order transaction is rolled back.
- The worker logs the event ID and order reference for processing failures, leaves failed events unprocessed, and backs off for the configured poll interval before retrying. An insufficient-stock event remains pending and is reported in the worker log.
- Setup and demo commands exit nonzero with a short explanation when PostgreSQL, the API, or a response is unavailable or invalid.

## Reproduce the two demonstrations

With API and worker running, submit the burst (three unique refs plus a repeat of the first):

```bash
python -m scripts.burst_demo
```

For the interruption/recovery case, stop the worker with Ctrl+C in its terminal. Leave the API running and run:

```bash
python -m scripts.outage_demo
```

The script prints stock before and during the pause and the accepted orders' statuses. Restart the worker:

```bash
python -m app.worker
```

Query the order references printed by the script again; they should reach `STOCK_UPDATED`. The daily report counts accepted orders while processing is paused, while its stock values show the current (possibly lagging) product table.

## Tests

Set `TEST_DATABASE_URL` to a dedicated PostgreSQL test database, then run:

```bash
python -m pytest -q
```

The integration checks create sample tables and test products in that database. Use a disposable database because test rows are retained. If no PostgreSQL URL is configured or the server cannot be reached, the PostgreSQL integration tests are skipped; SQLite is deliberately not substituted.

## Design notes

See [SOLUTION.md](SOLUTION.md) for schema, transaction boundaries, event processing, consistency semantics, and scope limits.
Use [VIDEO_DEMO.md](VIDEO_DEMO.md) as a timed recording and narration guide for the requested walkthrough.
