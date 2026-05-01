"""Token-bucket rate limiter, shared diskcache wrapper, and per-provider stats.

Every external client wraps a `RateLimiter` and goes through `cached_call`
so we get consistent observability and never hammer providers.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

import diskcache
import structlog

from config.settings import settings, ensure_runtime_dirs

log = structlog.get_logger(__name__)

ensure_runtime_dirs()
_cache = diskcache.Cache(str(settings.diskcache_dir))


@dataclass
class ProviderCounter:
    requests: int = 0
    cache_hits: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def reset(self) -> None:
        self.requests = 0
        self.cache_hits = 0
        self.started_at = time.monotonic()

    def effective_rps(self) -> float:
        elapsed = max(time.monotonic() - self.started_at, 1e-9)
        return self.requests / elapsed


_stats: dict[str, ProviderCounter] = defaultdict(ProviderCounter)
_stats_lock = threading.Lock()


def record_request(provider: str) -> None:
    with _stats_lock:
        _stats[provider].requests += 1


def record_cache_hit(provider: str) -> None:
    with _stats_lock:
        _stats[provider].cache_hits += 1


def snapshot_stats() -> dict[str, dict[str, float]]:
    with _stats_lock:
        return {
            name: {
                "requests": float(c.requests),
                "cache_hits": float(c.cache_hits),
                "effective_rps": c.effective_rps(),
            }
            for name, c in _stats.items()
        }


def log_and_reset_stats() -> dict[str, dict[str, float]]:
    """Log per-provider effective request rate and reset counters.

    Call once per refresh cycle so the user sees how close we're running
    to each provider's limit.
    """
    snap = snapshot_stats()
    if snap:
        log.info("provider_stats_cycle", stats=snap)
    with _stats_lock:
        for c in _stats.values():
            c.reset()
    return snap


@dataclass
class RateLimiter:
    """Simple token-bucket. Thread-safe and asyncio-safe."""

    rps: float
    burst: int
    _tokens: float = field(init=False)
    _last: float = field(init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.burst)
        self._last = time.monotonic()

    def _take(self) -> float:
        """Return seconds the caller should sleep before proceeding."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self.burst, self._tokens + elapsed * self.rps)
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return 0.0
            return (1.0 - self._tokens) / self.rps

    def acquire(self) -> None:
        delay = self._take()
        if delay > 0:
            time.sleep(delay)

    async def acquire_async(self) -> None:
        delay = self._take()
        if delay > 0:
            await asyncio.sleep(delay)


def cache_get(key: str) -> Any | None:
    return _cache.get(key)


def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    _cache.set(key, value, expire=ttl_seconds)


def cached_call(
    key: str,
    ttl_seconds: int,
    fn: Callable[[], Any],
    *,
    provider: str = "unknown",
) -> Any:
    """Return cached value if fresh, else call `fn` and cache the result.

    The wrapper logs every miss with the provider name so we can audit
    real call rates.
    """
    hit = _cache.get(key, default=_MISS)
    if hit is not _MISS:
        record_cache_hit(provider)
        return hit
    log.info("cache_miss", provider=provider, key=key)
    record_request(provider)
    value = fn()
    if value is not None:
        _cache.set(key, value, expire=ttl_seconds)
    return value


_MISS = object()
