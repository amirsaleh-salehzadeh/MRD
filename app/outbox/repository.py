from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OutboxEvent


def pending_events(session: Session, limit: int):
    """Return pending events in deterministic processing order."""
    return session.execute(
        select(OutboxEvent.event_id, OutboxEvent.payload)
        .where(OutboxEvent.processed_at.is_(None))
        .order_by(OutboxEvent.created_at, OutboxEvent.event_id)
        .limit(limit)
    ).all()
