# CLAUDE.md

> This file is the contract between the human and any AI assistant working on this project. It is the single source of truth for purpose, architecture, conventions, and operational state. **Keep it current.** When a non-obvious decision is made, update the relevant section in the same change. When something changes in production behavior (port, schedule, provider, schema), update it here before merging.

---

## 1. Project Purpose

A personal investment **decision-support dashboard** with three coordinated capabilities behind a near real-time web UI:

1. **Quantitative screener** over Indian (NSE Nifty 500) and US (NYSE / NASDAQ) equities. Filters: P/E < 20, today's volume > 2× 20-day average, RSI(14) > 50.
2. **Curated news & research feed** aggregated from multiple independent channels per market, with sentiment and category tagging.
3. **Portfolio + goal tracking + daily morning briefing.** User holdings, YTD return vs. a 50% annual target, rule-based entry/exit/hold signals, and a scheduled morning briefing delivered in-app and via email.

**Critical framing:** This is *decision support, not financial advice.* Every signal labels the rule that fired and the underlying numbers. The user is the decision-maker. A persistent disclaimer is required in the UI footer: *"Informational only. Not investment advice. You are responsible for your own trades."*

---

## 2. Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Mature finance / data ecosystem |
| UI framework | Streamlit | Fastest path to a dense data UI; sufficient for single-user near-real-time |
| Persistence | SQLite via SQLAlchemy | Single-user local app; zero ops; easy to back up |
| Scheduler | APScheduler embedded + optional cron entry point | App-embedded for default; cron for headless reliability |
| Concurrency | `asyncio` + `httpx` for I/O; bounded semaphores per provider | Respect rate limits cleanly |
| Caching | `diskcache` (multi-tier TTLs) | Persists across runs; no Redis dependency |
| Indicators | `pandas_ta` | Vetted RSI / DMA implementations |
| Sentiment | Provider-supplied first, `vaderSentiment` fallback | FinBERT deferred to v1.1 (compute cost) |
| News ingestion | API adapters + `feedparser` for RSS + `trafilatura` for body extraction; `rapidfuzz` for de-duplication | Source diversity is mandatory |
| LLM features | Optional, behind feature flag, via Anthropic API | AI summaries off by default |

---

## 3. Tech Stack & Pinned Dependencies

See `requirements.txt`. Notable:
- `yfinance`, `nsepython`, `pandas`, `pandas_ta`, `httpx`, `streamlit`, `apscheduler`, `sqlalchemy`, `diskcache`, `feedparser`, `trafilatura`, `rapidfuzz`, `vaderSentiment`, `pydantic`, `structlog`, `python-dotenv`, `pytest`.

---

## 4. Directory Layout

```
.
├── CLAUDE.md                 # this file
├── README.md                 # setup + run + troubleshooting
├── DECISIONS.md              # log of non-obvious trade-offs
├── requirements.txt
├── .env.example
├── .gitignore                # MUST exclude .env, briefings/, logs/, *.db
├── app.py                    # Streamlit entry point
├── scripts/
│   └── run.sh
├── config/
│   ├── settings.py           # pydantic Settings, reads .env
│   └── rules_default.yaml    # default signal rules
├── data_sources/
│   ├── universe.py           # Nifty 500, NYSE, NASDAQ ticker lists
│   ├── prices.py             # OHLCV fetch with caching + rate limit
│   └── fundamentals.py       # P/E, sector, name with longer-TTL cache
├── indicators/
│   └── technical.py          # RSI, DMA, volume ratio
├── screener/
│   ├── filters.py
│   └── runner.py             # screener.run(universe, filters)
├── news/
│   ├── aggregator.py         # news.fetch(market, tickers, sources, since)
│   ├── dedupe.py
│   ├── sentiment.py
│   └── sources/              # one adapter per channel (see §6)
├── portfolio/
│   ├── models.py             # SQLAlchemy models
│   ├── importer.py           # CSV + manual entry
│   └── valuation.py          # P&L, FX conversion
├── goals/
│   └── tracker.py            # YTD, gap, required CAGR, feasibility label
├── signals/
│   ├── rules.py              # entry / exit / hold rule engine
│   └── sizing.py             # position sizing helper
├── briefing/
│   ├── composer.py           # briefing.compose(...)
│   ├── scheduler.py          # APScheduler config
│   ├── run.py                # CLI entry: python -m briefing.run --date today
│   └── delivery/
│       ├── inapp.py
│       ├── email.py
│       └── slack.py          # optional
├── ui/
│   ├── pages/
│   │   ├── dashboard.py      # 3-panel main view
│   │   ├── briefing.py       # today + history
│   │   └── settings.py       # rules, schedule, providers
│   └── components/
├── tests/
│   ├── test_screener.py
│   ├── test_indicators.py
│   ├── test_news_dedupe.py
│   ├── test_signals.py
│   ├── test_goals.py
│   └── test_briefing.py
├── briefings/                # YYYY-MM-DD.{json,md} snapshots (gitignored)
├── logs/                     # rotated app.log (gitignored)
└── data/
    └── app.db                # SQLite (gitignored)
```

---

## 5. Data Sources & Rate Limits

> **Update this table whenever a provider is added, swapped, or hits its limit in practice.**

### Market data

| Provider | Used for | Free-tier limits | Strategy |
|---|---|---|---|
| `yfinance` | OHLCV, fundamentals (US + India) | Undocumented, observed ~2000 req/hr; bursty 429s | Batched multi-ticker download (50/batch); token-bucket 4 rps / burst 8; tenacity retry with exponential jitter, max 3 attempts |
| `nsepython` / NSE official | Nifty 500 constituents | Unofficial scraping; respect 1 req/sec | Cache constituents list 24h; falls back to last cached on failure |
| Wikipedia (S&P 500 + Nasdaq-100 articles) | NYSE / NASDAQ universe | None | `pd.read_html` over the article tables; cached 24h. Chosen over `nasdaqtrader.com` symbol files because those include thousands of ETFs/derivatives we'd have to filter — see DECISIONS.md D-009 |
| Finnhub `/news` + `/company-news` | Market + ticker news, sentiment passthrough | 60 calls/min (free) | Token-bucket 1 rps / burst 5; per-ticker calls only for screener-qualified + watchlist; 5-min cache; graceful skip when `FINNHUB_API_KEY` is unset |
| FX rate source | INR↔USD | TBD (yfinance `USDINR=X` default) | Cache 1h; fallback to `exchangerate.host` per DECISIONS.md D-007 |

### News & research

| Provider | Used for | Free-tier limits | Strategy |
|---|---|---|---|
| Finnhub | Ticker news, sentiment, recommendations, price targets | 60 calls/min (free) | Per-ticker calls only for held + screener-qualified |
| MarketAux | Aggregated market news (incl. India) | 100 calls/day (free) | Reserve for daily refresh, not per-tick |
| NewsAPI.org | Broad headlines | 100 calls/day (free, dev only) | Avoid in production paths |
| GNews | Backup aggregator | 100 calls/day (free) | Tertiary fallback |
| Alpha Vantage `NEWS_SENTIMENT` | Sentiment-tagged news | 25 calls/day (free) | Low-frequency batch only |
| RSS feeds | Source-specific (Moneycontrol, ET Markets, Livemint, Reuters, CNBC, MarketWatch, Yahoo, etc.) | None | Polled every news refresh |

### Caching tiers

| Data | TTL | Store |
|---|---|---|
| Universe (Nifty 500 / NYSE / NASDAQ tickers) | 24h | diskcache |
| Fundamentals (P/E, name, sector) | 1h | diskcache |
| 20-day historical volume | 30m | diskcache |
| Current price/volume | 30s during market hours | diskcache |
| News list per provider | 5m | diskcache |
| Article body | 24h | diskcache |
| FX rates | 1h | diskcache |

### Rate-limit pattern (mandatory)

- Every external client wraps a `RateLimiter(rps=..., burst=...)` (token bucket).
- 429/5xx → exponential backoff with jitter, max 3 retries, then graceful degradation (partial result + warning, never crash).
- Log effective request rate per provider every refresh cycle.
- UI footer shows live rate-limit status per provider.

---

## 6. Signal Rules (defaults — editable in UI)

### Entry signals (BUY candidate — applied to screener output + watchlist)
- **Required:** P/E < 20, today's volume > 2× 20-day avg, RSI(14) > 50.
- **Tiebreakers (configurable, default ON):** 50-DMA > 200-DMA, no earnings within 3 trading days.
- **Tiebreaker (configurable, default OFF):** non-negative news sentiment in last 24h.

### Exit signals (SELL candidate — applied to held positions)
- **Stop-loss:** −8% from cost basis (per-position editable).
- **Profit target:** +25% from cost basis (per-position editable).
- **Trailing stop:** 10% off recent high (post-entry).
- **Technical breakdown:** price < 50-DMA on volume > 1.5× 20-day avg.
- **Negative news cluster:** ≥3 negative-sentiment items in 24h.

### Hold
- Held position with no entry/exit rule firing → labeled "Hold (no rule fired)."

### Position sizing
- Max risk per trade: 2% of portfolio (configurable). Position size = (portfolio × 2%) / (entry − stop). Pure math, no opinion.
- **Note:** A 50% annual target is structurally hard to reconcile with 2%-per-trade sizing. The UI surfaces this tension in the goal panel.

---

## 7. Goal Tracking Math

- **YTD return** = (current portfolio value − starting capital) / starting capital, computed daily.
- **Gap to goal** = target % − YTD %.
- **Required remainder CAGR** = annualized return needed over remaining trading days to hit target. Recomputed on every dashboard load.
- **Feasibility label** thresholds:
  - *On track* — required remainder CAGR ≤ 12% annualized.
  - *Stretch* — 12–25%.
  - *Aggressive* — 25–50%.
  - *Highly improbable* — > 50% (top decile of historical market outcomes).
- Hovering the label reveals the specific math.
- **No green-washing.** If the math says highly improbable, the UI says so.

---

## 8. Daily Morning Briefing

- **Schedule:** 08:00 IST for NSE coverage, 07:30 ET for US coverage. Both run unless disabled.
- **Delivery:** in-app dashboard view + email (default). Slack/Telegram optional.
- **Persistence:** `./briefings/YYYY-MM-DD-{market}.{json,md}`.
- **Contents (in order):**
  1. One-line plain-English summary.
  2. Goal status: YTD %, gap, required remainder CAGR, feasibility label.
  3. Portfolio overnight movement (futures/ADR pre-market read, FX, top movers).
  4. Today's calendar: earnings on held tickers, ex-div, macro events, index rebalancing.
  5. Today's signals: exits on held positions (rule-named), entry candidates from screener+watchlist (rule-named), holds.
  6. News digest: top items aligned to held + watchlist, de-duped, with sentiment.
  7. Risk alerts: concentration > threshold, drawdown > threshold, single position > X% of portfolio.

---

## 9. Run & Dev Commands

```bash
# one-time
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in keys

# run the app (default port 8501)
streamlit run app.py
# or:
./scripts/run.sh

# run a briefing manually (for cron)
python -m briefing.run --date today --market nse
python -m briefing.run --date today --market us

# tests
pytest -q
```

**Default port:** `8501`. Override via `STREAMLIT_SERVER_PORT` in `.env`.

---

## 10. Conventions

- **Type hints everywhere.** `pydantic` models for any structured payload.
- **Logging:** `structlog`, level via `LOG_LEVEL` env var; rotated `./logs/app.log`. **No `print` in production paths.**
- **Errors:** never silently swallow. Log with context, return a typed error object, surface in UI when user-facing.
- **No hardcoded tickers, secrets, or paths.** Universe is fetched; secrets via `.env`; paths via `config/settings.py`.
- **Tests** live in `tests/`, named `test_<module>.py`. New behavior ships with at least a smoke test.
- **Module purity:** `screener.run`, `news.fetch`, `signals.evaluate`, `briefing.compose` are pure functions, UI-independent.
- **Disclaimer is non-removable.** Footer text is wired into the layout component, not a config flag.

---

## 11. Schema (SQLite)

> Tables created on app startup via `Base.metadata.create_all()` (DECISIONS.md D-008). Defined in `portfolio/models.py`.

| Table | Columns |
|---|---|
| `holdings` | id, ticker, exchange, quantity, avg_cost, purchase_date, currency, stop_loss_pct, profit_target_pct, trailing_stop_pct, high_since_entry |
| `watchlist` | id, ticker, exchange, added_at |
| `signals_history` | id, ticker, rule, direction, fired_at, price_at_fire, price_5d, price_20d, price_60d |
| `briefings` | id, market, generated_at, snapshot_path |
| `news_cache` | id, url (unique), headline, source, published_at, sentiment |
| `settings` | key (PK), value |

`settings` keys used by the app:
- `starting_capital_usd` — base capital for goal math
- `annual_target_pct` — e.g. `0.50`
- `goal_start_date` — ISO date

---

## 12. Known Trade-offs (link to DECISIONS.md for detail)

- NYSE / NASDAQ universe defaults to a curated subset: **S&P 500 + Nasdaq-100 (~600 unique tickers)**, fetched from Wikipedia and cached 24h (DECISIONS.md D-001, D-009). Full ~5,000-ticker listings require a paid feed.
- `yfinance` is the default OHLCV / fundamentals source despite known reliability issues; swap to Polygon or Finnhub paid via the `MarketDataProvider` interface when the user provides a key (DECISIONS.md D-002).
- News in v1 is single-provider (Finnhub free tier). MarketAux + RSS land in a follow-up; the dispatcher in `news/aggregator.py` already supports multi-source merge with URL+headline dedupe.
- RSI uses an iterative Wilder-seeded smoothing rather than `pandas.ewm(adjust=False)` because pandas seeds the EWM with the first observation while Wilder uses the SMA of the first `period` observations — the difference is meaningful and tests pin our values to Wilder's published 1978 fixture (DECISIONS.md D-010).
- Portfolio CSV importer auto-detects between the documented canonical schema and Fidelity's `Portfolio_Positions` export. Fidelity exports omit `purchase_date`; we default to Jan 1 of the current year (DECISIONS.md D-012).
- USDINR FX uses yfinance `USDINR=X` primary with `exchangerate.host` fallback after 3 consecutive yfinance failures (DECISIONS.md D-013).
- Briefing emails are multipart text+HTML; the HTML body is a naive markdown wrap (no extra dependency). Full-fidelity copy lives in the `.md` snapshot on disk (DECISIONS.md D-014).
- APScheduler `BackgroundScheduler` runs in-process inside Streamlit. `python -m briefing.run` is retained as a CLI entry point so users running headless can drive it via cron (DECISIONS.md D-015).
- AI summaries and broker integration are feature-flagged off in v1 (DECISIONS.md D-003).

---

## 13. Open Items

> Move items to DECISIONS.md once resolved.

- [x] SMTP provider — Gmail App Password (D-006). `.env.example` carries the
      required keys; any SMTP host works because the mailer only uses `smtplib`.
- [x] NSE vs US schedule — both run by default; `BRIEFING_COMBINE=true`
      collapses to a single combined email (D-005).
- [x] FX source — yfinance `USDINR=X` primary, `exchangerate.host` fallback
      after 3 consecutive failures (D-007 / D-013).
- [x] Backtest window — 1 year for v1, 3 years deferred to v1.1 (D-004).
      Implementation in `scripts/backtest.py`.
