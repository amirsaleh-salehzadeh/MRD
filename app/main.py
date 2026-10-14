from datetime import date
import logging

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.db import SessionLocal
from app.models import Product
from app.orders import (
    DuplicatePayloadConflict,
    OrderTotalTooLarge,
    UnknownSKU,
    create_order,
    get_order,
)
from app.reporting import daily_report
from app.schemas import OrderAccepted, OrderCreate

app = FastAPI(title="Mr D Orders & Stock", version="1.0.0")
logger = logging.getLogger("orders-api")


@app.exception_handler(OperationalError)
def database_unavailable(_request, exc: OperationalError):
    logger.error(
        "Database connection or operation failed",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})


@app.exception_handler(SQLAlchemyError)
def database_operation_failed(_request, exc: SQLAlchemyError):
    logger.error("Database operation failed", exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(status_code=500, content={"detail": "Database operation failed"})


@app.exception_handler(Exception)
def unexpected_error(_request, exc: Exception):
    logger.error("Unexpected request failure", exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _order_payload(order) -> dict:
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


@app.post("/orders", response_model=OrderAccepted, status_code=202)
def post_order(request: OrderCreate, response: Response):
    with SessionLocal() as session:
        try:
            order, duplicate = create_order(session, request)
        except DuplicatePayloadConflict:
            raise HTTPException(
                status_code=409, detail="order_ref already exists with a different payload"
            )
        except UnknownSKU as exc:
            raise HTTPException(status_code=422, detail=f"Unknown SKU: {exc}")
        except OrderTotalTooLarge as exc:
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


@app.get("/orders/{order_ref}")
def read_order(order_ref: str):
    with SessionLocal() as session:
        order = get_order(session, order_ref)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return _order_payload(order)


@app.get("/products/{sku}/stock")
def read_stock(sku: str):
    with SessionLocal() as session:
        product = session.get(Product, sku)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return {"sku": product.sku, "stock": product.stock}


@app.get("/reports/daily")
def read_daily_report(report_date: date = Query(alias="date")):
    with SessionLocal() as session:
        return daily_report(session, report_date)


@app.get("/health")
def health():
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Health check failed: database unavailable", exc_info=exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}
