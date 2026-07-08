"""Database setup: SQLite engine, session factory, declarative base.

The database lives in the add-on's persistent ``/data`` directory so it
survives add-on updates and restarts. For local development / tests, set the
``DATA_DIR`` environment variable to any writable folder.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "hose_assistant.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    # SQLite + FastAPI: the same connection may be used across threads.
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db():
    """FastAPI dependency: yield a session and always close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
