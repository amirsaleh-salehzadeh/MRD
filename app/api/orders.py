from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.schemas import OrderAccepted, OrderCreate
from app.db.models import Order

router = APIRouter()


def _main():
    # Resolve application dependencies at request time so the app remains easy to test.
    from app import main

    return main


def _order_payload(order: Order) -> dict:
    return {
        "id": str(order.id),
        "order_ref": order.order_ref,
        "customer_id": order.customer_id,
        "total_cents": order.total_cents,
        "status": order.status,
        "created_at": order.created_at,
        "items": [
            {
                "sku": item.sku,
                "qty": item.quantity,
                "unit_price_cents": item.unit_price_cents,
                "line_total_cents": item.line_total_cents,
            }
            for item in order.items
        ],
    }


@router.post("/api/v1/orders", response_model=OrderAccepted, status_code=202)
def post_order(request: OrderCreate, response: Response):
    main = _main()
    with main.SessionLocal() as session:
        try:
            order, duplicate = main.create_order(session, request)
        except main.DuplicatePayloadConflict:
            raise HTTPException(
                status_code=409, detail="order_ref already exists with a different payload"
            )
        except main.UnknownSKU as exc:
            raise HTTPException(status_code=422, detail=f"Unknown SKU: {exc}")
        except main.OrderTotalTooLarge as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if duplicate:
        response.status_code = 200
    return OrderAccepted(
        order_id=str(order.id),
        order_ref=order.order_ref,
        total_cents=order.total_cents,
        status=order.status,
        duplicate=duplicate,
    )


@router.get("/api/v1/orders/{order_id}")
def read_order_by_id(order_id: UUID):
    main = _main()
    with main.SessionLocal() as session:
        order = session.scalar(
            select(Order)
            .options(joinedload(Order.items))
            .where(Order.id == order_id)
        )
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return _order_payload(order)
