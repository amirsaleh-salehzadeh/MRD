"""Submit distinct orders while the separately-run worker is stopped."""

from datetime import datetime, timezone
import sys
import uuid

import httpx
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import OutboxEvent
from scripts.cli import checked_json, run_cli

BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    stamp = f"{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"
    orders = [
        {
            "order_ref": f"pause-{stamp}-1",
            "customer_id": "cust-pause-1",
            "items": [{"sku": "BAN-001", "qty": 1}],
        },
        {
            "order_ref": f"pause-{stamp}-2",
            "customer_id": "cust-pause-2",
            "items": [{"sku": "APL-003", "qty": 1}],
        },
    ]
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        skus = ("BAN-001", "APL-003")
        before = {sku: checked_json(client.get(f"/products/{sku}/stock"))["stock"] for sku in skus}
        accepted = [checked_json(client.post("/orders", json=order)) for order in orders]
        statuses = [
            checked_json(client.get(f"/orders/{order['order_ref']}"))["status"] for order in orders
        ]
        after = {sku: checked_json(client.get(f"/products/{sku}/stock"))["stock"] for sku in skus}
        with SessionLocal() as session:
            pending = session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.processed_at.is_(None))
            )
        print("Stop the worker before running this script.")
        print("Stock before/while paused:", before, after)
        print("Accepted orders:", accepted)
        print("Statuses while paused:", statuses)
        print("Pending outbox events (database-wide):", pending)
        if after != before or any(status != "PENDING_STOCK" for status in statuses):
            raise ValueError(
                "Stock changed during the demo; stop every stock worker and rerun with fresh order refs."
            )
        print(
            "Restart `python -m app.worker`, then query these order refs to confirm STOCK_UPDATED."
        )


if __name__ == "__main__":
    sys.exit(run_cli(main))
