from datetime import datetime, timezone
import time
import uuid
import sys

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
            "order_ref": f"web-{stamp}-045",
            "customer_id": "cust-42",
            "items": [{"sku": "BAN-001", "qty": 2}, {"sku": "APL-003", "qty": 1}],
        },
        {
            "order_ref": f"web-{stamp}-046",
            "customer_id": "cust-43",
            "items": [{"sku": "BAN-001", "qty": 1}, {"sku": "APL-003", "qty": 2}],
        },
        {
            "order_ref": f"web-{stamp}-047",
            "customer_id": "cust-44",
            "items": [{"sku": "APL-003", "qty": 1}, {"sku": "COF-005", "qty": 1}],
        },
    ]
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        before = {
            sku: checked_json(client.get(f"/products/{sku}/stock"))["stock"]
            for sku in ("BAN-001", "APL-003", "COF-005")
        }
        responses = [checked_json(client.post("/orders", json=order)) for order in orders]
        duplicate = checked_json(client.post("/orders", json=orders[0]))
        print("Before stock:", before)
        print("New orders:", responses)
        print("Duplicate:", duplicate)
        final_orders = []
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            final_orders = [
                checked_json(client.get(f"/orders/{order['order_ref']}")) for order in orders
            ]
            if all(order["status"] == "STOCK_UPDATED" for order in final_orders):
                break
            time.sleep(0.2)
        after = {sku: checked_json(client.get(f"/products/{sku}/stock"))["stock"] for sku in before}
        with SessionLocal() as session:
            pending = session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.processed_at.is_(None))
            )
        report = checked_json(
            client.get(
                "/reports/daily", params={"date": datetime.now(timezone.utc).date().isoformat()}
            )
        )
        print("After stock:", after)
        print("Accepted distinct orders in this burst:", len(responses))
        print("Duplicate submissions in this burst:", int(duplicate.get("duplicate", False)))
        print("Pending outbox events (database-wide):", pending)
        print("Final orders:", final_orders)
        print("Daily report:", report)
        if not duplicate.get("duplicate"):
            raise ValueError("Repeated order_ref was not reported as a duplicate")
        if not all(order["status"] == "STOCK_UPDATED" for order in final_orders):
            raise ValueError(
                "Worker did not finish the burst within five seconds; inspect its logs and pending events"
            )


if __name__ == "__main__":
    sys.exit(run_cli(main))
