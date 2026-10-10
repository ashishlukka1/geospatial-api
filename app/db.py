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
    """Pin the driver SQLAlchemy would otherwise choose by version default.

    Bare postgresql:// (and Heroku-style postgres://) resolves to whatever
    DBAPI the installed SQLAlchemy prefers — newer releases default to
    psycopg v3, which is not a project dependency and broke the Vercel
    import with ModuleNotFoundError. Force psycopg2, which is installed
    and covered by the test suite. URLs that already name a driver pass
    through untouched.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
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
