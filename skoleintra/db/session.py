from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Example: postgresql+psycopg://localhost/skoleintra
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg:///skoleintra")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
