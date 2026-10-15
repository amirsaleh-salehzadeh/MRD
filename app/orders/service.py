import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload

from app.db.models import Order, OrderItem, OutboxEvent, Product
from app.schemas import OrderCreate
from app.orders.repository import get_order


class DuplicatePayloadConflict(Exception):
    pass


class UnknownSKU(Exception):
    pass


class OrderTotalTooLarge(Exception):
    pass


def _request_fingerprint(request: OrderCreate) -> tuple[str, list[tuple[str, int]]]:
    # Preserve item order and duplicate SKU lines as submitted.
    return request.customer_id, [(line.sku, line.qty) for line in request.items]


def _existing_matches(order: Order, request: OrderCreate) -> bool:
    return (
        order.customer_id == request.customer_id
        and [(item.sku, item.quantity) for item in sorted(order.items, key=lambda x: x.id)]
        == _request_fingerprint(request)[1]
    )


def create_order(session: Session, request: OrderCreate) -> tuple[Order, bool]:
    normalized_items = _request_fingerprint(request)[1]
    with session.begin():
        # A conflict-safe insert serializes concurrent submissions by order_ref.
        order_id = uuid.uuid4()
        inserted = session.execute(
            insert(Order)
            .values(
                id=order_id,
                order_ref=request.order_ref,
                customer_id=request.customer_id,
                total_cents=0,
                status="PENDING_STOCK",
            )
            .on_conflict_do_nothing(index_elements=[Order.order_ref])
            .returning(Order.id)
        ).scalar_one_or_none()
        if inserted is None:
            existing = session.scalar(
                select(Order)
                .options(joinedload(Order.items))
                .where(Order.order_ref == request.order_ref)
            )
            if existing is None:
                raise RuntimeError("Order conflict occurred but the existing row was not visible")
            if not _existing_matches(existing, request):
                raise DuplicatePayloadConflict(request.order_ref)
            return existing, True

        products = {}
        for sku in sorted({sku for sku, _ in normalized_items}):
            product = session.get(Product, sku)
            if product is None:
                raise UnknownSKU(sku)
            products[sku] = product

        order = session.get(Order, order_id)
        event_items = []
        total = 0
        for sku, qty in normalized_items:
            product = products[sku]
            line_total = product.price_cents * qty
            total += line_total
            if total > 9_223_372_036_854_775_807:
                raise OrderTotalTooLarge("Order total exceeds the supported range")
            session.add(
                OrderItem(
                    order_id=order_id,
                    sku=sku,
                    quantity=qty,
                    unit_price_cents=product.price_cents,
                    line_total_cents=line_total,
                )
            )
            event_items.append({"sku": sku, "qty": qty, "unit_price_cents": product.price_cents})
        order.total_cents = total
        session.flush()
        event_id = uuid.uuid4()
        session.add(
            OutboxEvent(
                event_id=event_id,
                event_type="OrderAccepted",
                event_version=1,
                aggregate_id=order_id,
                payload={
                    "event_id": str(event_id),
                    "event_type": "OrderAccepted",
                    "event_version": 1,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "order_id": str(order_id),
                        "order_ref": request.order_ref,
                        "customer_id": request.customer_id,
                        "total_cents": total,
                        "items": event_items,
                    },
                },
            )
        )
        session.flush()
        result_order = session.scalar(
            select(Order).options(joinedload(Order.items)).where(Order.id == order_id)
        )
    if result_order is None:
        raise RuntimeError("Order transaction committed without returning the created order")
    return result_order, False
