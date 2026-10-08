"""Shared pytest setup: one throwaway database for the whole suite.

TESTING=1 is set before the app is imported so startup skips the
PostgreSQL connection. get_db is overridden once here, so every test
module talks to the same in-memory SQLite database.
"""

import os

os.environ["TESTING"] = "1"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=test_engine)
Base.metadata.create_all(bind=test_engine)


def override_get_db():
    """Give each request a session on the throwaway test database."""
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture()
def client():
    """Test client talking to the app with the test database."""
    return TestClient(app)


@pytest.fixture()
def db_session():
    """Direct session on the test database for asserting stored rows."""
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()
