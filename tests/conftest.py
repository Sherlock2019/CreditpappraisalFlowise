"""Shared fixtures. API tests run the real FastAPI app on SQLite; pgvector retrieval is stubbed."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bank-credit-ai-poc" / "backend"))

# Must be set before app.config is imported anywhere.
os.environ.setdefault("AUTH_DEV_MODE", "true")
os.environ.setdefault("AUTH_DEV_JWT_SECRET", "test-only-dev-secret-not-for-real-use-0123456789")
os.environ.setdefault("AGENT_TOKEN_SECRET", "test-only-agent-secret-not-for-real-use-0123456789")
os.environ.setdefault("AUDIT_LOG_DIR", str(ROOT / ".pytest_cache" / "audit_logs"))

import pytest  # noqa: E402
from pgvector.sqlalchemy import Vector  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(Vector, "sqlite")
def _vector_on_sqlite(type_, compiler, **kw):
    return "BLOB"


@pytest.fixture()
def db_session_factory():
    from app import models  # noqa: F401  (registers tables)
    from app.database import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    engine.dispose()
