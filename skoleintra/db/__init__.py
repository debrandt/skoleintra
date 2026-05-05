"""Database engine and session helpers used by the runtime entrypoints."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from skoleintra.db.models import Base  # noqa: F401 — re-exported for alembic

_STATE: dict[str, sessionmaker | None] = {"session_local": None}


def init_db(database_url: str) -> None:
    """Initialise the SQLAlchemy engine and session factory.

    Must be called once before using ``get_session()``.
    """
    engine = create_engine(database_url)
    _STATE["session_local"] = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )


def get_session() -> Session:
    """Return a new SQLAlchemy session.

    Caller is responsible for commit/rollback and closing.
    """
    session_local = _STATE["session_local"]
    if session_local is None:
        raise RuntimeError("Database not initialised — call init_db() first.")
    return session_local()


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
