from datetime import date
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.api.orders import router as orders_router
from app.api.products import router as products_router
from app.db.session import SessionLocal
from app.orders.service import (
    DuplicatePayloadConflict,
    OrderTotalTooLarge,
    UnknownSKU,
    create_order,
    get_order,
)
from app.reporting import daily_report

app = FastAPI(title="Mr D Orders & Stock", version="1.0.0")
app.include_router(orders_router)
app.include_router(products_router)
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
