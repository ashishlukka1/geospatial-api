"""Database connection setup.

The engine is created once when this module loads and is reused
for every request. A new Session is opened per request through
the get_db dependency and closed when the request finishes.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()


def _normalize_url(url: str) -> str:
    """Accept the Heroku-style postgres:// scheme SQLAlchemy rejects."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Set it in your .env file (local) "
        "or environment variables (hosted)."
    )
DATABASE_URL = _normalize_url(DATABASE_URL)

# connect_timeout bounds cold-start hangs when the host is unreachable
# instead of blocking a serverless instance indefinitely.
engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 10})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Parent class for all database models."""

    pass


def get_db():
    """Yield a database session for one request, then close it."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
