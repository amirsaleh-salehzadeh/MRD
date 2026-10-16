import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.inventory import apply_event
from app.models import Base, Order, OutboxEvent, Product, StockEventApplication
from app.orders import DuplicatePayloadConflict, OrderTotalTooLarge, UnknownSKU, create_order
from app.reporting import daily_report
from app.schemas import OrderCreate


def test_order_request_rejects_unrepresentable_quantities_and_oversized_lists():
    base = {"order_ref": "bounds", "customer_id": "cust", "items": [{"sku": "SKU", "qty": 1}]}
    for qty in (0, -1, 2_147_483_648):
        with pytest.raises(ValidationError):
            OrderCreate(**{**base, "items": [{"sku": "SKU", "qty": qty}]})
    with pytest.raises(ValidationError):
        OrderCreate(
            **{
                **base,
                "items": [{"sku": f"SKU-{index}", "qty": 1} for index in range(101)],
            }
        )


@pytest.fixture
def db_engine():
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration checks")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_server_side_price_snapshot_and_deduplication(db_engine):
    reference = f"pytest-{uuid.uuid4()}"
    with Session(db_engine, expire_on_commit=False) as session:
        with session.begin():
            session.merge(Product(sku="TEST-1", name="Test", price_cents=123, stock=10))
        request = OrderCreate(
            order_ref=reference, customer_id="cust", items=[{"sku": "TEST-1", "qty": 2}]
        )
        order, duplicate = create_order(session, request)
        assert not duplicate
        assert order.total_cents == 246
        assert order.items[0].unit_price_cents == 123
        order_id = order.id
        repeat, duplicate = create_order(session, request)
        assert duplicate and repeat.id == order_id
        changed = OrderCreate(
            order_ref=reference, customer_id="cust", items=[{"sku": "TEST-1", "qty": 1}]
        )
        with pytest.raises(DuplicatePayloadConflict):
            create_order(session, changed)
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.aggregate_id == order_id)
            )
            == 1
        )
        session.commit()


def test_concurrent_identical_submissions_create_one_order_and_event(db_engine):
    reference = f"pytest-concurrent-{uuid.uuid4()}"
    request = OrderCreate(
        order_ref=reference,
        customer_id="cust-concurrent",
        items=[{"sku": "TEST-1", "qty": 1}],
    )

    def submit():
        with Session(db_engine, expire_on_commit=False) as session:
            order, duplicate = create_order(session, request)
            return order.id, duplicate

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _index: submit(), range(6)))
    assert len({order_id for order_id, _duplicate in results}) == 1
    assert sum(not duplicate for _order_id, duplicate in results) == 1
    with Session(db_engine) as session:
        order_id = results[0][0]
        assert (
            session.scalar(select(func.count()).select_from(Order).where(Order.id == order_id)) == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.aggregate_id == order_id)
            )
            == 1
        )


def test_worker_applies_stock_once(db_engine):
    reference = f"pytest-{uuid.uuid4()}"
    with Session(db_engine, expire_on_commit=False) as session:
        with session.begin():
            session.merge(Product(sku="TEST-2", name="Test", price_cents=100, stock=10))
        request = OrderCreate(
            order_ref=reference, customer_id="cust", items=[{"sku": "TEST-2", "qty": 3}]
        )
        order, _ = create_order(session, request)
        event_id = session.scalar(
            select(OutboxEvent.event_id).where(OutboxEvent.aggregate_id == order.id)
        )
        session.commit()
        assert apply_event(session, event_id) == "processed"
        assert apply_event(session, event_id) == "skipped"
        assert session.get(Product, "TEST-2").stock == 7
        assert session.get(Order, order.id).status == "STOCK_UPDATED"
        assert session.get(StockEventApplication, event_id) is not None


def test_orders_are_accepted_while_worker_is_paused_and_report_counts_them(db_engine):
    reference = f"pytest-{uuid.uuid4()}"
    with Session(db_engine, expire_on_commit=False) as session:
        with session.begin():
            session.merge(Product(sku="TEST-3", name="Test", price_cents=50, stock=8))
        request = OrderCreate(
            order_ref=reference, customer_id="cust", items=[{"sku": "TEST-3", "qty": 2}]
        )
        order, _ = create_order(session, request)
        # No worker is invoked: acceptance/reporting proceed while inventory remains pending.
        assert order.status == "PENDING_STOCK"
        assert session.get(Product, "TEST-3").stock == 8
        report = daily_report(session, datetime.now(timezone.utc).date())
        assert report["accepted_orders"] >= 1
        assert report["units_sold_per_sku"]["TEST-3"] >= 2
        assert report["stock_may_lag"] is True
        event_id = session.scalar(
            select(OutboxEvent.event_id).where(OutboxEvent.aggregate_id == order.id)
        )
        session.commit()
        assert apply_event(session, event_id) == "processed"  # resume: catch up the paused order
        assert session.get(Product, "TEST-3").stock == 6
        assert session.get(Order, order.id).status == "STOCK_UPDATED"


def test_http_read_surfaces(db_engine, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=db_engine, expire_on_commit=False))
    with Session(db_engine, expire_on_commit=False) as session:
        with session.begin():
            session.merge(Product(sku="TEST-4", name="Test", price_cents=80, stock=9))

    reference = f"pytest-{uuid.uuid4()}"
    with TestClient(main.app) as client:
        payload = {
            "order_ref": reference,
            "customer_id": "cust",
            "items": [{"sku": "TEST-4", "qty": 2}],
        }
        accepted = client.post("/api/v1/orders", json=payload)
        assert accepted.status_code == 202
        assert accepted.json()["total_cents"] == 160
        repeated = client.post("/api/v1/orders", json=payload)
        assert repeated.status_code == 200
        assert repeated.json()["duplicate"] is True
        assert repeated.json()["order_id"] == accepted.json()["order_id"]
        changed_payload = {**payload, "items": [{"sku": "TEST-4", "qty": 3}]}
        assert client.post("/api/v1/orders", json=changed_payload).status_code == 409
        unknown_payload = {
            "order_ref": f"{reference}-unknown",
            "customer_id": "cust",
            "items": [{"sku": "NO-SUCH-SKU", "qty": 1}],
        }
        assert client.post("/api/v1/orders", json=unknown_payload).status_code == 422
        assert (
            client.get(f"/api/v1/orders/{accepted.json()['order_id']}")
            .json()["items"][0]["unit_price_cents"]
            == 80
        )
        assert client.get(f"/api/v1/orders/{uuid.uuid4()}").status_code == 404
        assert client.get("/api/v1/products/TEST-4/stock").json()["stock"] == 9
        assert client.get("/api/v1/products/NO-SUCH-SKU/stock").status_code == 404
        assert client.get("/health").status_code == 200
        assert client.post("/orders", json=payload).status_code == 404
        assert client.get("/orders/legacy-reference").status_code == 404
        assert client.get("/products/TEST-4/stock").status_code == 404
        report = client.get(
            "/reports/daily", params={"date": datetime.now(timezone.utc).date().isoformat()}
        )
        assert report.status_code == 200
        assert report.json()["units_sold_per_sku"]["TEST-4"] >= 2
    with Session(db_engine) as session:
        order_id = uuid.UUID(accepted.json()["order_id"])
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.aggregate_id == order_id)
            )
            == 1
        )
        assert (
            session.scalar(select(Order).where(Order.order_ref == unknown_payload["order_ref"]))
            is None
        )


def test_order_endpoint_returns_sanitized_errors(monkeypatch):
    from app import main

    class EmptySession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(main, "SessionLocal", EmptySession)
    body = {
        "order_ref": "error-case",
        "customer_id": "cust",
        "items": [{"sku": "BAN-001", "qty": 1}],
    }
    with TestClient(main.app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(
            main,
            "create_order",
            lambda *_args: (_ for _ in ()).throw(DuplicatePayloadConflict("error-case")),
        )
        assert client.post("/api/v1/orders", json=body).status_code == 409

        monkeypatch.setattr(
            main, "create_order", lambda *_args: (_ for _ in ()).throw(UnknownSKU("UNKNOWN"))
        )
        assert client.post("/api/v1/orders", json=body).status_code == 422

        monkeypatch.setattr(
            main,
            "create_order",
            lambda *_args: (_ for _ in ()).throw(
                OrderTotalTooLarge("Order total exceeds the supported range")
            ),
        )
        oversized = client.post("/api/v1/orders", json=body)
        assert oversized.status_code == 422
        assert oversized.json() == {"detail": "Order total exceeds the supported range"}

        monkeypatch.setattr(
            main,
            "create_order",
            lambda *_args: (_ for _ in ()).throw(
                OperationalError("insert", {}, RuntimeError("offline"))
            ),
        )
        unavailable = client.post("/api/v1/orders", json=body)
        assert unavailable.status_code == 503
        assert unavailable.json() == {"detail": "Database temporarily unavailable"}

        monkeypatch.setattr(
            main,
            "create_order",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("private detail")),
        )
        failed = client.post("/api/v1/orders", json=body)
        assert failed.status_code == 500
        assert failed.json() == {"detail": "Internal server error"}
