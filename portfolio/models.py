"""SQLAlchemy 2.0 models for portfolio + signal history + briefings.

Engine and session factory are lazy: the first call to `get_engine()` runs
`Base.metadata.create_all()`. No Alembic in v1 (DECISIONS.md D-008).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator, Optional

from sqlalchemy import Date, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from config.settings import ensure_runtime_dirs, settings


class Base(DeclarativeBase):
    pass


class Holding(Base):
    __tablename__ = "holdings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    exchange: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)
    purchase_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(5))
    stop_loss_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_target_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trailing_stop_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high_since_entry: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    exchange: Mapped[str] = mapped_column(String(10))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SignalRecord(Base):
    __tablename__ = "signals_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    rule: Mapped[str] = mapped_column(String(50))
    direction: Mapped[str] = mapped_column(String(10))   # entry | exit | hold
    fired_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    price_at_fire: Mapped[float] = mapped_column(Float)
    price_5d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_20d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_60d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class BriefingMeta(Base):
    __tablename__ = "briefings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market: Mapped[str] = mapped_column(String(10))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    snapshot_path: Mapped[str] = mapped_column(String(500))


class NewsCacheRow(Base):
    __tablename__ = "news_cache"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    headline: Mapped[str] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(100))
    published_at: Mapped[datetime] = mapped_column(DateTime)
    sentiment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


class UserSetting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(2000))


_engine = None
_SessionLocal: Optional[sessionmaker[Session]] = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        ensure_runtime_dirs()
        _engine = create_engine(settings.database_url_resolved, future=True)
        Base.metadata.create_all(_engine)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


@contextmanager
def get_session() -> Iterator[Session]:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_user_setting(key: str, default: str | None = None) -> str | None:
    with get_session() as s:
        row = s.get(UserSetting, key)
        return row.value if row else default


def set_user_setting(key: str, value: str) -> None:
    with get_session() as s:
        row = s.get(UserSetting, key)
        if row is None:
            s.add(UserSetting(key=key, value=value))
        else:
            row.value = value
