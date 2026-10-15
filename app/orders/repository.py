from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Order


def get_order(session: Session, order_ref: str) -> Order | None:
    return session.scalar(
        select(Order).options(joinedload(Order.items)).where(Order.order_ref == order_ref)
    )
