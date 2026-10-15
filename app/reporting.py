from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Order, OrderItem, Product


def daily_report(session: Session, report_date: date) -> dict:
    start = datetime.combine(report_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    accepted_count, revenue = session.execute(
        select(func.count(Order.id), func.coalesce(func.sum(Order.total_cents), 0)).where(
            Order.created_at >= start, Order.created_at < end
        )
    ).one()
    units = dict(
        session.execute(
            select(OrderItem.sku, func.sum(OrderItem.quantity))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.created_at >= start, Order.created_at < end)
            .group_by(OrderItem.sku)
        ).all()
    )
    stock = dict(session.execute(select(Product.sku, Product.stock)).all())
    return {
        "date": report_date.isoformat(),
        "accepted_orders": int(accepted_count),
        "revenue_cents": int(revenue),
        "units_sold_per_sku": {sku: int(qty) for sku, qty in sorted(units.items())},
        "current_stock_per_sku": {sku: int(qty) for sku, qty in sorted(stock.items())},
        "stock_may_lag": True,
    }
