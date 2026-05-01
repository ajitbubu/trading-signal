"""SQLAlchemy models. `Base.metadata.create_all()` is called on app startup
when the portfolio milestone lands; until then this module is import-safe
but the engine is created lazily.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from config.settings import settings


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


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    exchange: Mapped[str] = mapped_column(String(10))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SignalHistory(Base):
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


class NewsCache(Base):
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
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(settings.database_url_resolved, future=True)
        Base.metadata.create_all(_engine)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session():
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal()
