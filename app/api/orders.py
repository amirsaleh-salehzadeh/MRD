from fastapi import APIRouter, HTTPException, Response

from app.schemas import OrderAccepted, OrderCreate

router = APIRouter()


def _main():
    # Resolve application dependencies at request time so the app remains easy to test.
    from app import main

    return main


@router.post("/orders", response_model=OrderAccepted, status_code=202)
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


@router.get("/orders/{order_ref}")
def read_order(order_ref: str):
    main = _main()
    with main.SessionLocal() as session:
        order = main.get_order(session, order_ref)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return main._order_payload(order)
