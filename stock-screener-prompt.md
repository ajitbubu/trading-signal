# Prompt: Build a Real-Time Stock Screener + Market News + Personal Goal-Tracking Dashboard (NSE Nifty 500 / NYSE / NASDAQ)

## Role
You are a senior Python engineer. Build a production-quality **personal investment decision-support dashboard** with three coordinated capabilities behind a near real-time web UI:
1. A quantitative screener over Indian and US equities.
2. A curated news/research feed aggregated from multiple channels.
3. A personal portfolio + goal-tracking layer with a daily morning briefing.

**Critical framing — this is decision support, not financial advice.** The user is the decision-maker. The app surfaces signals based on rules the user configures, computes goal-progress math honestly (including realistic-vs-aspirational gaps), and never auto-executes trades. Every "buy / sell / hold" indicator must be labeled as a *signal* with its underlying rule shown, plus a persistent disclaimer in the UI footer: *"Informational only. Not investment advice. You are responsible for your own trades."*

Optimize for correctness, observability, and respecting third-party API rate limits over speed of delivery.

---

## Mandatory Process (do these in order)

1. **Ask clarifying questions first.** Do not write a single line of code until I answer the questions in the *Pre-Implementation Questions* section below. List them in one batch.
2. **Initialize the project and create `CLAUDE.md` at the repo root before any source code.** It must capture: project purpose, architecture decisions, tech stack, directory layout, data-source choices, rate-limit strategy, run/dev commands, and conventions (naming, logging, error handling). Treat `CLAUDE.md` as the contract — keep it updated as decisions change.
3. **Confirm the chosen port** (default suggestion: `8501` for Streamlit, `8050` for Dash, `8000` for FastAPI). State it explicitly in `CLAUDE.md` and in the run instructions.
4. **Provide setup & run steps** in a `README.md`: prerequisites, virtualenv creation, `requirements.txt` install, environment variables, and the exact command to start the app along with the URL (e.g., `http://localhost:8501`).

---

## Functional Requirements

### Market selection (user input)
- A dropdown in the UI to pick one of:
  - **NSE — Nifty 500** (India)
  - **NYSE** (US)
  - **NASDAQ** (US — Nasdaq Composite or Nasdaq-100, confirm scope with me)
  - **US — Combined (NYSE + NASDAQ)** as an optional aggregate view
- The universe must be fetched dynamically (do not hardcode tickers in source).
  - **Nifty 500:** pull the official constituent list from NSE.
  - **NYSE / NASDAQ:** use the NASDAQ Trader symbol directory (`nasdaqlisted.txt`, `otherlisted.txt`) or an equivalent maintained source, filtered by exchange.
  - If rate limits make full coverage impractical on free APIs, fall back to a curated large/mid-cap subset (e.g., S&P 500 for NYSE-heavy, Nasdaq-100 for NASDAQ) and **flag this trade-off explicitly in `CLAUDE.md`**.

### Screening filters (apply in this order)
1. **P/E ratio < 20** (trailing P/E; skip tickers with null/negative earnings unless I say otherwise).
2. **Volume spike > 2× the 20-day average daily volume.**
3. **RSI(14) > 50** on daily candles.

### Output
- Ranked table of qualifying stocks. Columns: **Ticker, Company Name, Current Price, P/E, Volume Ratio (today ÷ 20-day avg), RSI(14)**.
- Default ranking: by **Volume Ratio descending** (confirm with me — see questions).
- Show last-refresh timestamp and the number of tickers scanned vs. qualified.

### Near real-time behavior
- Auto-refresh on a configurable interval (default 60 seconds during market hours, paused outside).
- Indicate market open/closed status for the selected exchange in its local timezone (IST for NSE, ET for NYSE/NASDAQ).
- During refresh, show a non-blocking loading state — never blank the table.

### News & Research Feed (second panel)
A coordinated panel that surfaces market news and analyst/research content alongside the screener.

**Scope of content**
- **General market news** for the selected market (NSE / NYSE / NASDAQ): index moves, macro, sector rotation, regulatory.
- **Ticker-specific news** for stocks currently in the qualified screener result.
- **Research & analyst coverage:** broker upgrades/downgrades, price-target changes, earnings previews/recaps, sell-side notes where accessible.
- **Curated channel coverage:** allow the user to select which sources to include/exclude.

**Required source diversity (aggregate from multiple channels)**
- **Indian sources:** Moneycontrol, Economic Times Markets, Livemint, Business Standard, NSE/BSE corporate announcements, SEBI filings.
- **US sources:** Reuters, Bloomberg (where licensable / via free RSS), CNBC, MarketWatch, Yahoo Finance, Seeking Alpha, Benzinga, NASDAQ.com.
- **Global/wires:** AP, AFP, Financial Times (headlines via RSS).
- **Aggregator APIs (recommended):** Finnhub `/news` and `/news-sentiment`, Polygon `/v2/reference/news`, MarketAux, NewsAPI.org, Alpha Vantage `NEWS_SENTIMENT`, GNews. Use whichever I authorize.
- **RSS fallback:** for any source without an API, ingest the public RSS feed.
- **Do not rely on a single provider.** Configure at least 3 independent sources per market and de-duplicate by URL/title-similarity.

**Per-item display fields**
- Headline, source/channel, published timestamp (localized), short summary/snippet, link to full article, related ticker(s), and — if available — sentiment label (positive/neutral/negative) and category tag (earnings, M&A, macro, regulatory, analyst-action).

**Filtering & UX**
- Filters: by source, by category, by sentiment, by ticker, by time window (1h / 4h / 24h / 7d).
- A "Linked to screener results" toggle that restricts the feed to tickers currently passing the screen.
- Search box across headlines.
- Manual "Mark as read" / hide is nice-to-have, not required for v1.

**Refresh behavior**
- News refresh interval independent of price refresh (default 5 minutes; configurable).
- Show source-by-source freshness so the user can see if any channel is stale or rate-limited.

**Optional but encouraged**
- Lightweight on-device sentiment scoring (e.g., VADER or FinBERT via `transformers`) when the provider doesn't supply sentiment. Document compute cost in `CLAUDE.md`.
- An "AI summary" button per ticker that synthesizes the day's news into 3 bullets — gated behind a feature flag and only if I authorize an LLM API.

### Portfolio, Goal Tracking & Morning Briefing (third panel)

A coordinated panel that connects the user's actual holdings to the screener and news, tracks progress toward an annual return target, and produces a daily morning briefing.

**Portfolio ingestion**
- Manual entry via UI form *and* CSV import. Required fields per holding: ticker, exchange, quantity, average cost, purchase date, currency.
- Optional: broker integration (Zerodha Kite, Upstox, Interactive Brokers, Alpaca) — gated behind a feature flag and only if I provide credentials.
- Compute and persist: current market value, unrealized P&L (absolute + %), weight in portfolio, sector, days held.
- Multi-currency support: portfolio total in a base currency the user picks (default INR or USD); FX from a reliable source with caching.

**Goal tracking**
- User configures: **annual return target (default 50%)**, target start date (default Jan 1 of current year), and base capital.
- Continuously compute and display:
  - **YTD return** (absolute and %), realized vs. unrealized split.
  - **Gap to goal** in % and absolute terms.
  - **Required CAGR for remainder of year** to still hit target — recomputed daily.
  - **Feasibility indicator** comparing required remainder-CAGR to historical market norms; show a calibrated label such as *"On track / Stretch / Aggressive / Highly improbable"* with the threshold logic visible on hover. **Do not soften the math** — if the required return for the rest of the year is unrealistic, say so plainly.
  - **Risk metrics:** rolling 30-day volatility, max drawdown YTD, Sharpe (if a benchmark is configured), concentration risk (top 3 positions as % of portfolio).
  - **Benchmark comparison:** portfolio return vs. Nifty 500 / S&P 500 / NASDAQ-100 YTD.

**Signal engine (buy / sell / hold candidates)**
- The app does **not** issue advice. It evaluates user-defined rules and labels each ticker accordingly. Every signal must show *which rule fired* and *the data behind it*.
- **Rule types the user can configure** (sensible defaults provided, all editable in the UI):
  - **Entry signals** (BUY candidate) — applied to screener output and watchlist:
    - Screener filters pass (P/E < 20, Vol > 2× 20-day avg, RSI > 50).
    - Optional overlays: 50-DMA above 200-DMA, positive news sentiment in last 24h, no earnings within next 3 trading days.
  - **Exit signals** (SELL candidate) — applied to held positions:
    - Stop-loss hit (default −8% from cost basis, configurable per position).
    - Profit target hit (default +25%, configurable per position).
    - Trailing stop (default 10% off recent high).
    - Technical breakdown (price < 50-DMA on rising volume).
    - Negative news sentiment cluster (≥3 negative items in 24h).
  - **Hold signals** — held positions where neither entry nor exit rules fire; show "no action indicated by current rules."
- **Position-sizing helper:** given the user's available cash and a max-risk-per-trade % (default 2% of portfolio), suggest a position size for each BUY candidate based on stop distance. Pure math, no opinion.

**Daily morning briefing**
- Generated and delivered at a user-configured time per market (defaults: **08:00 IST** for NSE, **07:30 ET** for US markets — configurable).
- Delivery channels: in-app dashboard view, email, and optionally Slack/Telegram (only if I provide credentials).
- **Briefing contents** (in this order):
  1. **Goal status:** YTD return, gap to 50% target, required CAGR for remainder, feasibility label.
  2. **Portfolio overnight movement:** futures/ADR pre-market read, currency moves, top 3 movers in your holdings.
  3. **Today's calendar:** earnings releases for held tickers, ex-dividend dates, macro events (FOMC, RBI, CPI, jobs), index rebalancing.
  4. **Today's signals:**
     - Held positions hitting any **exit rule** (with the specific rule named).
     - Watchlist / screener tickers hitting any **entry rule**.
     - Held positions on **hold** (no rule fired).
  5. **News digest:** top 5–10 items aligned to held tickers + watchlist, de-duplicated, with sentiment.
  6. **Risk alerts:** concentration > threshold, drawdown > threshold, single position > X% of portfolio.
  7. **One-line plain-English summary** at the very top (e.g., *"3 exit signals, 2 entry candidates, goal status: Stretch — need 4.1%/month for remainder."*).
- Briefing must be reproducible: persist a snapshot to disk (`./briefings/YYYY-MM-DD.json` + `.md`) so the user can review history and the app can compute signal hit-rate over time.

**Backtesting & honesty checks (recommended for v1.1, scoped in v1)**
- Track every signal the app surfaced and compare against subsequent 5/20/60-day price action. Display rolling **signal hit-rate** in the UI. This is the single most important honesty mechanism — the user can see whether the rules actually work before committing capital.
- Provide a simple historical backtest of the current rule set over the past 1–3 years on the selected market.

---

## Technical Requirements

### Suggested stack (propose alternatives in your questions if you disagree)
- **Language:** Python 3.11+
- **Market data:** `yfinance` as the default free source; `nsepython` or NSE official endpoints for Nifty 500 constituents. If I authorize a paid provider (Polygon, Finnhub, Alpha Vantage, EODHD), prefer it for reliability.
- **News & research ingestion:** `feedparser` for RSS; provider SDKs or `httpx` for Finnhub / Polygon / MarketAux / NewsAPI / Alpha Vantage / GNews; `newspaper3k` or `trafilatura` for article body extraction when only a link is available; `rapidfuzz` for de-duplication.
- **Sentiment (if local):** `vaderSentiment` for fast baseline; `transformers` + a FinBERT model behind a feature flag for higher quality.
- **Indicators:** `pandas_ta` or `ta` for RSI; do not hand-roll RSI unless explicitly justified.
- **UI:** Streamlit (fastest path) — propose Dash or FastAPI + simple React if you have a strong reason. The two-panel layout (screener + news) should be designed as side-by-side or tabbed.
- **Concurrency:** `asyncio` + `httpx` or a bounded `ThreadPoolExecutor` for parallel ticker and news fetches.
- **Caching:** `requests-cache` or `diskcache` for fundamentals (P/E changes slowly); short TTL for prices/volume; medium TTL (5–15 min) for news lists; long TTL for already-fetched article bodies.

### Rate-limit strategy (must be in `CLAUDE.md`)
- Document the rate limit of every external API used.
- Implement a **token-bucket or semaphore-bounded fetcher** with exponential backoff + jitter on 429/5xx.
- **Batch** wherever the API supports it (e.g., yfinance multi-ticker download).
- **Cache** fundamentals (P/E, name) for at least 1 hour; cache 20-day historical volume for at least 30 minutes.
- On a full Nifty 500 / NYSE scan, stagger requests so total runtime stays inside the provider's per-minute/per-hour ceiling. Log the effective request rate.
- Provide a graceful degradation path: if rate-limited, return partial results with a clear warning rather than crashing.

### Code quality
- Type hints throughout; `pydantic` models for any structured payload.
- Logging via `structlog` or stdlib `logging` with a configurable level — no `print` statements in production paths.
- Separate modules: `data_sources/`, `indicators/`, `screener/`, `news/` (with `news/sources/` per-channel adapters and `news/aggregator.py`), `portfolio/`, `goals/`, `signals/`, `briefing/` (with `briefing/delivery/` for email/Slack/Telegram adapters), `ui/`, `config/`.
- A pure `screener.run(universe, filters)` function that is independently unit-testable without the UI.
- A pure `news.fetch(market, tickers, sources, since)` function that is independently unit-testable without the UI.
- A pure `signals.evaluate(portfolio, watchlist, rules, market_data, news)` function that returns labeled signals with the firing rule attached.
- A pure `briefing.compose(date, portfolio, signals, news, calendar, goal)` function that returns a structured briefing object renderable as Markdown, HTML email, or JSON.
- At least smoke tests for: ticker-list fetch, RSI calculation against a known fixture, filter application, rate-limiter behavior, news source adapter (mocked), de-duplication logic, signal-rule evaluation, goal feasibility math, and briefing composition (snapshot test).

---

## UI/UX Requirements

**Layout: three coordinated panels (tabbed or grid)**
- **Screener panel:** dense sortable table with search, market selector, refresh-interval selector, and "Refresh now" button.
- **News & Research panel:** scrollable feed with source / category / sentiment / time-window filters and a "Linked to screener results" toggle.
- **Portfolio & Goal panel:** holdings table, goal progress widget (YTD %, gap to target, required remainder CAGR, feasibility label), risk metrics, and today's signals (entry / exit / hold) grouped by category.
- A dedicated **"Today's Briefing"** view (its own page or modal) that displays the full morning briefing for the current date and lets the user browse historical briefings.
- Layout must be responsive — collapse to tabs on narrow viewports.

**Cross-panel interactions**
- Clicking a ticker in the screener filters the news panel to that ticker and shows whether it's already held in the portfolio.
- Clicking a held position opens its full context: cost basis, P&L, applicable signals (with rules shown), recent news.
- Editing a stop-loss or target in the portfolio immediately updates the signal panel.

**Screener table styling**
- Color-code Volume Ratio (≥3× highlighted) and RSI (>70 amber as overbought warning).

**News feed styling**
- Each card shows source/channel badge, timestamp (relative + absolute on hover), headline, snippet, sentiment chip (if available), and category tag.
- De-duplicated across sources; show a small "+N similar" indicator when an item was reported by multiple channels.

**Goal & signals styling**
- Goal progress as a clear gauge or progress bar with **honest labeling** — if the required remainder CAGR is unrealistic, the label says so. No misleading green/optimistic visuals.
- Every signal card shows: ticker, signal type (Entry / Exit / Hold), the **rule that fired** in plain language, and the underlying numbers.

**Footer**
- Data source(s) in use, last refresh per panel, next refresh countdowns, rate-limit status per provider, **and a persistent disclaimer:** *"Informational only. Not investment advice. You are responsible for your own trades."*

---

## Operational Requirements

- **Port:** state it clearly in your first response. Default to `8501` unless you have a reason to choose otherwise.
- **Run command:** single command (e.g., `streamlit run app.py`) plus a `make run` or `./scripts/run.sh` wrapper.
- **Env vars:** any API keys (data, news, email/Slack/Telegram, broker) must come from `.env` (provide `.env.example`); never commit secrets.
- **Persistence:** SQLite by default for portfolio, signals history, briefings, and news cache. Provide a clear schema migration path. Document in `CLAUDE.md` how to back up the DB.
- **Scheduler:** the morning briefing requires a scheduled job. Use APScheduler embedded in the app process for simplicity, with the schedule configurable via the UI. Document the alternative (system cron + a CLI entry point `python -m briefing.run --date today`) in `CLAUDE.md` for users who don't want to keep the app running.
- **Logs:** written to `./logs/app.log` with rotation. Briefings additionally written to `./briefings/YYYY-MM-DD.{json,md}`.

---

## Deliverables

1. `CLAUDE.md` (created **first**, before code).
2. `README.md` with setup + run + port + troubleshooting.
3. `requirements.txt` (pinned versions).
4. `.env.example`.
5. Source tree following the module split above.
6. Minimal tests under `tests/`.
7. A short `DECISIONS.md` log if you make non-obvious trade-offs.

---

## Pre-Implementation Questions to Ask Me

Before writing code, ask me at least the following (add more if needed):

**Screener**
1. **Refresh interval:** Is 60 seconds acceptable, or do I need sub-minute? (Sub-minute will materially change the data-source choice.)
2. **Ranking metric:** Volume Ratio descending by default — confirm? Or do I want a composite score (e.g., weighted RSI + Volume Ratio + inverse P/E)?
3. **Top-N cap:** Show all qualifying or cap at top 25 / 50 / 100?
4. **Data provider:** Stick with free `yfinance` (with its known unreliability and undocumented rate caps), or do I have an API key for a paid provider?
5. **NASDAQ scope:** Full NASDAQ listing (~3,300 tickers), Nasdaq-100, or Nasdaq Composite large/mid-cap subset?
6. **Coverage trade-off for NYSE/NASDAQ:** Acceptable to start with a curated large/mid-cap subset and expand later?
7. **RSI period:** Standard 14 — confirm?
8. **P/E definition:** Trailing P/E only, or also accept forward P/E when trailing is unavailable?
9. **Negative/null P/E handling:** Exclude entirely (default), or include with a flag?

**News & Research**
10. **News providers:** Which do I have API keys for — Finnhub, Polygon, MarketAux, NewsAPI, Alpha Vantage, GNews? Any I should *not* use?
11. **Indian sources priority:** Confirm Moneycontrol, ET Markets, Livemint, Business Standard, NSE/BSE filings — anything to add or drop?
12. **US sources priority:** Confirm Reuters, CNBC, MarketWatch, Yahoo Finance, Seeking Alpha, Benzinga — anything to add or drop?
13. **Sell-side / analyst research:** Headlines-only via aggregators, or do I have access to a research feed (e.g., TipRanks, Refinitiv, Bloomberg Terminal export)?
14. **News refresh interval:** 5 minutes default — confirm?
15. **Sentiment:** Provider-supplied only, or also run local VADER/FinBERT scoring as a fallback?
16. **AI summaries:** Do you want a per-ticker LLM summary feature behind a flag? If yes, which model/provider?
17. **Time window default:** 24h on first load — confirm?

**Portfolio, Goal & Briefing**
18. **Base capital and start date for the goal:** What is the portfolio's starting value and start date for the 50% target (e.g., Jan 1 of this year, or a custom date)?
19. **Base currency:** INR or USD for portfolio reporting? How should multi-currency holdings be converted, and which FX source?
20. **Holdings ingestion:** Manual + CSV is the default. Do you want broker integration (Zerodha Kite, Upstox, IBKR, Alpaca) in v1, or v2?
21. **Stop-loss / profit-target defaults:** Confirm −8% stop, +25% target, 10% trailing — or set your own.
22. **Position-sizing rule:** Confirm 2% max risk per trade, or specify a different cap.
23. **Signal overlays:** Should entry signals require all overlays (50/200-DMA cross, positive sentiment, no near-term earnings) or treat them as "nice to have" tiebreakers?
24. **Briefing delivery:** In-app only, or also email / Slack / Telegram? If email, which SMTP provider? If Slack/Telegram, do you have webhook/bot tokens?
25. **Briefing schedule:** 08:00 IST for NSE and 07:30 ET for US — confirm, or specify.
26. **Benchmark:** Nifty 500 for Indian holdings and S&P 500 for US, or different benchmarks?
27. **Backtesting / hit-rate tracking:** Required in v1, or v1.1?
28. **Honesty bias:** Confirm you want the goal panel to label aggressive scenarios plainly (e.g., *"Highly improbable: required remainder return of 4.1%/month is in the top 1% of historical outcomes"*) rather than soft-pedaling the math.

**Cross-cutting**
29. **Persistence:** SQLite default — confirm? Or do you want Postgres / a different store?
30. **Export:** CSV/Excel download for screener, news, portfolio, and briefings — needed for v1 or later?
31. **Authentication:** Single-user local app, or does this need login (multi-user)?
32. **Deployment target:** Local only, or do I need a Dockerfile / cloud-deploy hints?
33. **UI framework preference:** Streamlit OK, or do you want me to recommend an alternative based on the refresh-rate answer?

---

## Acceptance Criteria

- I can run one command, open the stated port in a browser, pick NSE / NYSE / NASDAQ, and see a ranked screener table refreshing on the configured interval **alongside a news feed** drawing from at least 3 independent channels for that market.
- Clicking a ticker in the screener filters the news panel to that ticker and shows whether it is held in the portfolio.
- I can enter or import my portfolio, set a 50% annual return target, and the dashboard shows YTD return, gap to goal, required remainder CAGR, and a calibrated feasibility label that is honest about aggressive math.
- Every signal (Entry / Exit / Hold) is labeled with the rule that fired and the underlying numbers — never as raw advice.
- A morning briefing is generated daily at the configured time, persisted to disk, viewable in the UI, and (if configured) delivered to email/Slack/Telegram.
- A persistent disclaimer is visible: *"Informational only. Not investment advice. You are responsible for your own trades."*
- No filter is silently skipped; if a ticker is excluded due to missing data, that's logged and counted.
- News items are de-duplicated across sources and tagged by source/category/sentiment where available.
- Running the app twice in quick succession does **not** trip rate limits on either market data or news APIs (caches are working).
- `CLAUDE.md` accurately describes the running system, including all news providers, their rate limits, the portfolio schema, the signal rules, and the briefing schedule.
