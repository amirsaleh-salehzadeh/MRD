from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, or_, select

from app.db.models import OutboxEvent
from app.db.session import SessionLocal

router = APIRouter()


def _event_view(event: OutboxEvent) -> dict:
    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "event_version": event.event_version,
        "aggregate_id": str(event.aggregate_id),
        "payload": event.payload,
        "created_at": event.created_at,
    }


@router.get("/api/v1/events")
def list_events(
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    with SessionLocal() as session:
        statement = select(OutboxEvent).order_by(
            OutboxEvent.created_at, OutboxEvent.event_id
        )
        if cursor is not None:
            anchor = session.get(OutboxEvent, cursor)
            if anchor is None:
                raise HTTPException(status_code=404, detail="Event cursor not found")
            statement = statement.where(
                or_(
                    OutboxEvent.created_at > anchor.created_at,
                    and_(
                        OutboxEvent.created_at == anchor.created_at,
                        OutboxEvent.event_id > anchor.event_id,
                    ),
                )
            )
        page = session.scalars(statement.limit(limit + 1)).all()
        has_more = len(page) > limit
        events = page[:limit]
        return {
            "items": [_event_view(event) for event in events],
            "next_cursor": str(events[-1].event_id) if has_more and events else None,
        }


@router.get("/api/v1/events/{event_id}")
def read_event(event_id: UUID):
    with SessionLocal() as session:
        event = session.get(OutboxEvent, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return _event_view(event)
