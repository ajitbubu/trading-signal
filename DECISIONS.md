# DECISIONS

> Append-only log of non-obvious trade-offs. Newest at top. Each entry
> references the section in `CLAUDE.md` it amends or expands.

---

## 2026-05-01 — Initial scaffold

### D-001: NYSE / NASDAQ universe defaults to a curated subset
**Context:** §5 (Data Sources). Free APIs cannot sustain a full ~5,000-ticker
US scan within rate-limit budgets.
**Decision:** Default US universe = S&P 500 + Nasdaq-100 (~600 unique
tickers after de-dup). User can promote any additional ticker into the
watchlist; watchlist tickers are always scanned.
**Revisit when:** user provides a paid feed key (Polygon, Finnhub paid,
EODHD). Swap path: change `UniverseSource` impl in `data_sources/universe.py`.

### D-002: `yfinance` is the default OHLCV / fundamentals source
**Context:** §3 / §5. `yfinance` has known reliability issues but no key
is required and it covers both NSE and US.
**Decision:** Wrap `yfinance` behind a `MarketDataProvider` interface. All
calls go through one rate-limited adapter. When the user provides Finnhub or
Polygon keys, register an alternate provider; the screener picks providers
by priority order from `config/settings.py`.
**Revisit when:** observed 429 rate consistently exceeds 10% over a week.

### D-003: AI summaries off by default
**Context:** §10. LLM calls cost money and ship a sharp dependency.
**Decision:** `ENABLE_AI_SUMMARIES=false` in `.env.example`. UI shows the
button only when the flag is on AND `ANTHROPIC_API_KEY` is non-empty. First
click of a session shows an estimated cost based on cached summary count.

### D-004: Backtest window — 1 year for v1
**Context:** §13 open item. 3-year backtest is more honest but blows the
rate-limit budget for free providers and adds days to first-ship.
**Decision:** v1 ships with 1-year backtest of the current rule-set.
v1.1 extends to 3 years once `signals_history` has accumulated organic data.

### D-005: Briefing schedule — both markets, separate emails by default
**Context:** §13 open item. NSE and US run on different timezones; the user
is in NJ but tracks both.
**Decision:** Run both. Two emails by default (`BRIEFING_COMBINE=false`).
Setting `BRIEFING_COMBINE=true` produces one email at the earlier of the
two scheduled times with both market sections concatenated.

### D-006: SMTP via Gmail App Password
**Context:** §13 open item. Cheapest path with a no-ops setup; SendGrid free
tier requires domain verification.
**Decision:** Default to Gmail SMTP (smtp.gmail.com:587, STARTTLS, App
Password). README documents the App Password creation step. Swappable: any
SMTP host works because the email module only uses `smtplib`.

### D-007: FX source — `yfinance USDINR=X` primary, exchangerate.host fallback
**Context:** §13 open item.
**Decision:** Default to yfinance. If three consecutive fetches return null
or stale-by->2h data, the FX module logs a warning and uses
`https://api.exchangerate.host/latest?base=USD&symbols=INR` (no key, free,
generous limits) for that refresh cycle.

### D-008: SQLite, single file, no migrations framework in v1
**Context:** §3 / §11. Single-user local app; Alembic adds ceremony.
**Decision:** Schema is created via `Base.metadata.create_all()` on startup.
When a non-additive schema change is needed, add a migration script in
`scripts/migrations/` and document in this log. Promote to Alembic in v2.

### D-009: NYSE / NASDAQ constituents fetched via Wikipedia, not nasdaqtrader.com
**Context:** §5 originally listed `nasdaqtrader.com` symbol files
(`nasdaqlisted.txt`, `otherlisted.txt`).
**Decision:** Use `pd.read_html` over the public Wikipedia articles for
S&P 500 and Nasdaq-100. The nasdaqtrader files include thousands of
ETFs, ADRs, warrants, and preferred shares we'd have to filter, while
the Wikipedia tables are clean and structured. Both sources are equally
fragile to upstream changes; Wikipedia parses faster and lines up with
yfinance's symbol conventions. Cached 24h via diskcache.
**Revisit when:** the universe's curated subset is no longer enough — at
that point we adopt nasdaqtrader files plus a sector/instrument-type
filter, or move to a paid feed.

### D-010: RSI uses iterative Wilder seed + smoothing, not pandas EWM
**Context:** §6. The naive vectorized `ewm(alpha=1/period, adjust=False)`
approach seeds with the first observation, while Wilder (1978) seeds
with the SMA of the first `period` gains/losses. The difference produces
RSI values 5–20 points off Wilder's published example.
**Decision:** Implement RSI iteratively: SMA seed at index `period`,
then `avg_t = (avg_{t-1} * (period - 1) + x_t) / period` afterwards.
Pinned to Wilder's canonical 19-bar fixture in `tests/test_indicators.py`.
Performance hit is negligible for our O(500 tickers × 60 bars) workload.
**Revisit when:** universe grows >5,000 tickers or we move RSI to
intraday bars. At that point, vectorize via a hybrid SMA-then-EWM trick.

### D-011: Step 4 strip — overshoot stubs removed
**Context:** First-session scope per `answers-prefilled.md` is Steps 1–4
(scaffold + screener + news). The initial scaffold included pure-function
stubs for `goals/`, `signals/`, `portfolio/`, `briefing/` ahead of fence.
**Decision:** Stripped per user direction (option B) to keep PR #1's diff
matching the scope. Stubs will be re-introduced — with implementations,
not contracts — in the Step 5–9 session.
