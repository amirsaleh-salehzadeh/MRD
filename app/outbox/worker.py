import logging
import signal
import time

from sqlalchemy.exc import SQLAlchemyError

from app.config import POLL_INTERVAL_SECONDS, WORKER_BATCH_SIZE
from app.db.session import SessionLocal
from app.inventory.service import InsufficientStock, apply_event
from app.outbox.repository import pending_events

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("stock-worker")
stopping = False


def _stop(_signum, _frame):
    global stopping
    stopping = True


def run() -> None:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    logger.info(
        "worker started; poll_interval=%s batch_size=%s", POLL_INTERVAL_SECONDS, WORKER_BATCH_SIZE
    )
    while not stopping:
        try:
            with SessionLocal() as session:
                pending = pending_events(session, WORKER_BATCH_SIZE)
        except SQLAlchemyError:
            logger.exception("Failed to poll the outbox; retrying after the poll interval")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        except Exception:
            logger.exception("Unexpected polling failure; retrying after the poll interval")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        if not pending:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        had_error = False
        for event_id, envelope in pending:
            if stopping:
                break
            order_ref = envelope.get("payload", {}).get("order_ref", "unknown")
            try:
                with SessionLocal() as session:
                    result = apply_event(session, event_id)
                logger.info("event_id=%s order_ref=%s result=%s", event_id, order_ref, result)
            except InsufficientStock:
                had_error = True
                logger.exception(
                    "event_id=%s order_ref=%s insufficient stock; event left pending",
                    event_id,
                    order_ref,
                )
            except Exception:
                had_error = True
                logger.exception(
                    "event_id=%s order_ref=%s processing failed; event left pending",
                    event_id,
                    order_ref,
                )
        if had_error and not stopping:
            time.sleep(POLL_INTERVAL_SECONDS)
    logger.info("worker stopped")


if __name__ == "__main__":
    run()
