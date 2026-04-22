from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from skoleintra.db.models import Base  # noqa: F401 — re-exported for alembic

_SessionLocal: sessionmaker | None = None


def init_db(database_url: str) -> None:
    """Initialise the SQLAlchemy engine and session factory.

    Must be called once before using ``get_session()``.
    """
    global _SessionLocal
    engine = create_engine(database_url)
    _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Session:
    """Return a new SQLAlchemy session.

    Caller is responsible for commit/rollback and closing.
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    return _SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager that commits on success and rolls back on exception."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
