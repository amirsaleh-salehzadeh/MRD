from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database() -> None:
    # Deterministic local schema initializer; safe to run repeatedly.
    from app import models  # noqa: F401

    models.Base.metadata.create_all(bind=engine)
