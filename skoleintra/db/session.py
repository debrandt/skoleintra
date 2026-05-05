"""Shared SQLAlchemy engine and session factory for request-scoped database access."""

# pylint: disable=invalid-name

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from skoleintra.settings import get_settings

# Example: postgresql+psycopg://localhost/skoleintra
DATABASE_URL = get_settings().database_url or "postgresql+psycopg:///skoleintra"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
