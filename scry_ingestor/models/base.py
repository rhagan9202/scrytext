"""SQLAlchemy base declarations and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, close_all_sessions, sessionmaker

from ..utils.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None
_MODELS_IMPORTED = False



def _load_models() -> None:
    """Import model modules so metadata is aware of mapped classes."""

    global _MODELS_IMPORTED
    if _MODELS_IMPORTED:
        return

    import_module("scry_ingestor.models.ingestion_record")
    _MODELS_IMPORTED = True


def _create_engine() -> Engine:
    """Instantiate the SQLAlchemy engine using configured database URL."""

    settings = get_settings()
    database_url = settings.database_url or "sqlite:///./scry_ingestor.db"

    connect_args: dict[str, object] = {}
    pool_kwargs: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    else:
        pool_config = settings.database
        pool_kwargs = {
            "pool_size": pool_config.pool_size,
            "max_overflow": pool_config.max_overflow,
            "pool_timeout": pool_config.timeout,
            "pool_pre_ping": pool_config.pre_ping,
        }
        if pool_config.recycle_seconds > 0:
            pool_kwargs["pool_recycle"] = pool_config.recycle_seconds

    return create_engine(
        database_url,
        echo=False,
        future=True,
        connect_args=connect_args,
        **pool_kwargs,
    )


def get_engine() -> Engine:
    """Return (and lazily initialize) the shared SQLAlchemy engine."""

    global _ENGINE
    if _ENGINE is None:
        _ENGINE = _create_engine()
        _load_models()
        Base.metadata.create_all(bind=_ENGINE)
    return _ENGINE


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory bound to the global engine."""

    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        engine = get_engine()
        _SESSION_FACTORY = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _SESSION_FACTORY


def get_session() -> Session:
    """Retrieve a new SQLAlchemy session instance."""

    return get_session_factory()()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""

    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:  # pragma: no cover - ensure rollback on any failure
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Reset cached engine and session factory (useful for testing)."""

    global _ENGINE, _SESSION_FACTORY, _MODELS_IMPORTED
    if _SESSION_FACTORY is not None:
        close_all_sessions()
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SESSION_FACTORY = None
    _MODELS_IMPORTED = False
