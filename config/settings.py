"""Application settings, sourced from .env via pydantic-settings.

All paths and tunables live here. No hardcoded values elsewhere in the codebase.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Literal

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # paths
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    logs_dir: Path = ROOT / "logs"
    briefings_dir: Path = ROOT / "briefings"
    diskcache_dir: Path = ROOT / "diskcache"

    # streamlit
    streamlit_server_port: int = 8501

    # logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # database
    database_url: str = "sqlite:///data/app.db"

    # news provider api keys
    finnhub_api_key: str | None = None
    marketaux_api_key: str | None = None
    gnews_api_key: str | None = None
    alphavantage_api_key: str | None = None

    # llm feature flag
    enable_ai_summaries: bool = False
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"

    # smtp
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    briefing_email_from: str | None = None
    briefing_email_to: str | None = None
    briefing_combine: bool = False

    # refresh cadence
    price_refresh_seconds: int = 60
    news_refresh_seconds: int = 300

    # rate limit knobs
    yfinance_concurrency: int = 8
    provider_max_retries: int = 3

    # signal defaults (overridable via UI; persisted to settings table)
    pe_max: float = 20.0
    volume_ratio_min: float = 2.0
    rsi_period: int = 14
    rsi_min: float = 50.0
    stop_loss_pct: float = -0.08
    profit_target_pct: float = 0.25
    trailing_stop_pct: float = 0.10
    max_risk_per_trade_pct: float = 0.02
    annual_target_pct: float = 0.50

    # universe scope
    nasdaq_scope: Literal["nasdaq100", "all"] = "nasdaq100"
    nyse_scope: Literal["sp500", "all"] = "sp500"

    @property
    def database_url_resolved(self) -> str:
        if self.database_url.startswith("sqlite:///") and not self.database_url.startswith(
            "sqlite:////"
        ):
            relative = self.database_url[len("sqlite:///") :]
            return f"sqlite:///{(ROOT / relative).as_posix()}"
        return self.database_url


settings = Settings()


def ensure_runtime_dirs() -> None:
    for p in (settings.data_dir, settings.logs_dir, settings.briefings_dir, settings.diskcache_dir):
        p.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    ensure_runtime_dirs()
    log_path = settings.logs_dir / "app.log"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=5
    )
    handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(message)s",
        handlers=handlers,
    )

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, settings.log_level)),
        cache_logger_on_first_use=True,
    )
