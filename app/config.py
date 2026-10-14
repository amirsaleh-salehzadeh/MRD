import math
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/mrd_orders",
)

try:
    POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "1.0"))
except ValueError as exc:
    raise ValueError("POLL_INTERVAL_SECONDS must be a valid number") from exc

try:
    WORKER_BATCH_SIZE = int(os.getenv("WORKER_BATCH_SIZE", "25"))
except ValueError as exc:
    raise ValueError("WORKER_BATCH_SIZE must be a valid integer") from exc

if not math.isfinite(POLL_INTERVAL_SECONDS) or POLL_INTERVAL_SECONDS <= 0:
    raise ValueError("POLL_INTERVAL_SECONDS must be greater than zero")
if WORKER_BATCH_SIZE <= 0:
    raise ValueError("WORKER_BATCH_SIZE must be greater than zero")
