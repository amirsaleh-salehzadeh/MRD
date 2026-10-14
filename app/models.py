import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price_cents >= 0 AND stock >= 0"),)

    sku: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_ref", name="uq_orders_order_ref"),
        CheckConstraint("total_cents >= 0"),
        CheckConstraint("status IN ('PENDING_STOCK', 'STOCK_UPDATED')"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_ref: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[str] = mapped_column(Text, nullable=False)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_STOCK")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0"),
        CheckConstraint("unit_price_cents >= 0 AND line_total_cents >= 0"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True
    )
    sku: Mapped[str] = mapped_column(Text, ForeignKey("products.sku"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("event_version = 1"),
        CheckConstraint("event_type = 'OrderAccepted'"),
        UniqueConstraint("aggregate_id", "event_type", name="uq_outbox_order_event_type"),
        Index(
            "ix_outbox_pending_created",
            "created_at",
            "event_id",
            postgresql_where=text("processed_at IS NULL"),
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockEventApplication(Base):
    __tablename__ = "stock_event_applications"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outbox_events.event_id"), primary_key=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
