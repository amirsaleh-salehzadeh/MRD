from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Order, OutboxEvent, Product, StockEventApplication


class InsufficientStock(Exception):
    pass


def apply_event(session: Session, event_id) -> str:
    """Apply one event atomically; returns processed or skipped."""
    with session.begin():
        event = session.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.event_id == event_id)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            return "skipped"
        if session.get(StockEventApplication, event.event_id):
            event.processed_at = event.processed_at or datetime.now(timezone.utc)
            return "skipped"

        quantities = {}
        for item in event.payload["payload"]["items"]:
            quantities[item["sku"]] = quantities.get(item["sku"], 0) + int(item["qty"])
        for sku in sorted(quantities):
            qty = quantities[sku]
            result = session.execute(
                update(Product)
                .where(Product.sku == sku, Product.stock >= qty)
                .values(stock=Product.stock - qty)
            )
            if result.rowcount != 1:
                raise InsufficientStock(
                    f"Cannot apply {event.event_id}: insufficient stock for {sku}"
                )

        session.add(StockEventApplication(event_id=event.event_id, order_id=event.aggregate_id))
        session.execute(
            update(Order).where(Order.id == event.aggregate_id).values(status="STOCK_UPDATED")
        )
        from sqlalchemy import func

        event.processed_at = func.now()
    return "processed"
