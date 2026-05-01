# Pre-Filled Answers — Stock Screener + News + Goal Dashboard

> **For the AI agent:** These are the user's decisions for the 33 pre-implementation questions. Treat them as final. Proceed directly to scaffolding `CLAUDE.md` (already provided) and the project skeleton. **Re-ask only if an answer is genuinely ambiguous or if a value below is marked `[USER TO FILL]`.**

---

## Screener (1–9)

**1. Refresh interval — 60 seconds.**
Acceptable. Sub-minute is not required and would force a paid data feed. Auto-refresh pauses outside market hours for the selected exchange.

**2. Ranking metric — Volume Ratio descending (default), with composite score as a configurable alternative.**
Default sort = Volume Ratio descending. Expose a config toggle for a composite score: `0.4 × normalized(VolumeRatio) + 0.3 × normalized(RSI) + 0.3 × normalized(1/PE)`. Both rankings should be available in the UI.

**3. Top-N cap — Show 50 in the UI; CSV/Excel export contains all qualifying.**

**4. Data provider — Start with `yfinance` (free) plus Finnhub free tier where it adds value.**
No paid data subscription yet. Architect the data-source layer behind an interface so swapping to Polygon, Finnhub paid, or EODHD later is one config change. Document the swap path in `DECISIONS.md`.

**5. NASDAQ scope — Nasdaq-100 + selected mid-caps (~250 tickers).**
Full NASDAQ (~3,300) is impractical on free APIs. Start with Nasdaq-100. Allow the user to add specific tickers manually via watchlist for any mid-cap not in the default set.

**6. NYSE coverage trade-off — S&P 500 subset for v1.**
Yes, start with S&P 500 (most are NYSE-listed; a few are NASDAQ — that's fine, they belong in the US universe regardless). Expand to broader NYSE in v1.1 if the rate-limit budget allows.

**7. RSI period — 14. Confirmed.**

**8. P/E definition — Trailing P/E primary; fall back to forward P/E when trailing is null/negative; flag which one was used per row.**
Add a small `(F)` indicator in the P/E column when forward was substituted.

**9. Negative/null P/E handling — Exclude by default. UI toggle to include them with a flag.**

---

## News & Research (10–17)

**10. News providers — Free tiers of Finnhub, MarketAux, GNews, plus RSS for source-specific feeds. Avoid NewsAPI.org in production paths (commercial-use restriction).**
Sign-up order of priority for API keys: (1) Finnhub — best ticker-specific coverage and free sentiment / recommendations / price targets, (2) MarketAux — good India coverage, (3) GNews — backup. Alpha Vantage NEWS_SENTIMENT may be added later for sentiment-tagged batches (25/day is too tight for primary).

**11. Indian sources — Confirmed and expanded.**
Use: Moneycontrol, Economic Times Markets, Livemint, Business Standard, NSE/BSE corporate announcements, SEBI filings, Bloomberg Quint (BQ Prime). Include all where RSS or API access is available.

**12. US sources — Confirmed and expanded.**
Use: Reuters, CNBC, MarketWatch, Yahoo Finance, Seeking Alpha, Benzinga, NASDAQ.com, plus Bloomberg / WSJ / FT for headline-only via RSS where licensable.

**13. Sell-side / analyst research — Headlines + Finnhub free endpoints only.**
Use Finnhub `/stock/recommendation` (consensus rating trends) and `/stock/price-target` (analyst price targets) for the v1 research view. No paid research feed in v1.

**14. News refresh interval — 5 minutes. Confirmed.**
Independent of the price-refresh interval.

**15. Sentiment — Provider-supplied first, local VADER as fallback.**
Use Finnhub's sentiment when present; VADER (`vaderSentiment`) for items without a provider score. Defer FinBERT to v1.1 — the compute and dependency cost isn't justified for v1.

**16. AI summaries — Yes, behind a feature flag, OFF by default.**
Use the Anthropic API (model: latest Sonnet) when the user enables the flag and provides an API key in `.env`. Per-ticker summary triggers a single completion call, cached 1 hour. Show estimated cost in the UI before the first call of each session.

**17. Time window default — 24h on first load. Confirmed.**

---

## Portfolio, Goal & Briefing (18–28)

**18. Base capital and goal start date — `[USER TO FILL]`.**
Provide a UI form on first run that captures: starting portfolio value (in base currency), goal start date (default Jan 1 of current year), and target return % (default 50%). Persist to `settings` table. **Do not hardcode.** The agent should generate the form, but real values come from the user at runtime.

**19. Base currency — USD. FX via yfinance `USDINR=X` for any NSE holdings, cached 1 hour.**
User is US-based (NJ). Portfolio totals reported in USD. Per-position display shows native currency with USD conversion alongside. If yfinance FX proves unreliable in practice, swap to exchangerate.host (free, no key) — log this in `DECISIONS.md`.

**20. Holdings ingestion — Manual entry + CSV import in v1. Broker integration deferred to v2.**
CSV schema documented in README: `ticker, exchange, quantity, avg_cost, purchase_date, currency`. Provide a downloadable template. Broker integrations (Schwab, Fidelity, Zerodha, IBKR) require OAuth flows and are scoped for v2.

**21. Stop-loss / profit-target / trailing-stop defaults — Confirmed.**
−8% stop, +25% target, 10% trailing. All editable per-position in the UI. Persist overrides to the `holdings` table.

**22. Position-sizing rule — 2% max risk per trade (default), with a warning when this conflicts with the 50% goal.**
Keep 2% as the safe default. **However:** the goal panel should surface the structural tension — at 2% risk per trade with a typical win rate, hitting 50% annually requires either a high signal hit-rate, large average winners, or both. Show this calculation in the goal feasibility tooltip. Do not auto-raise the risk %.

**23. Signal overlays — Tiebreakers, not hard requirements.**
Entry candidates appear if the three core filters pass (P/E < 20, Volume > 2× avg, RSI > 50). Overlays (50/200-DMA cross, no near-term earnings, sentiment) are scored as tiebreakers and shown as badges on each card. The user can promote any overlay to "required" in settings.

**24. Briefing delivery — In-app + email in v1.**
SMTP via Gmail App Password (cheapest, fastest setup). `.env.example` includes `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `BRIEFING_EMAIL_TO`. Slack and Telegram are scoped for v1.1.

**25. Briefing schedule — Run both. 08:00 IST (NSE) and 07:30 ET (US).**
Two scheduled jobs, two snapshots written, two emails (or one combined — provide a config flag `BRIEFING_COMBINE=true`). User can disable either market in settings.

**26. Benchmark — Nifty 500 for INR holdings, S&P 500 for USD holdings; portfolio composite weighted by allocation.**
Show all three numbers in the goal panel: NSE allocation vs. Nifty 500, US allocation vs. S&P 500, total vs. weighted composite.

**27. Backtesting / hit-rate tracking — Required in v1.**
This is the honesty layer and non-negotiable. Every signal surfaced is logged to `signals_history` with subsequent 5/20/60-day price action. UI shows rolling hit-rate per rule. Historical backtest of the current rule-set over the past 1 year on each market — full 3-year backtest deferred to v1.1.

**28. Honesty bias — Confirmed.**
Goal feasibility labels are blunt. Required-remainder-CAGR > 50% annualized → label reads *"Highly improbable — top decile of historical outcomes."* No softening. Color the gauge accordingly (no green when the math says aggressive).

---

## Cross-cutting (29–33)

**29. Persistence — SQLite via SQLAlchemy. Confirmed.**
Single `data/app.db` file. Document backup procedure in `CLAUDE.md` and `README.md` (it's just `cp data/app.db data/app.db.bak.YYYYMMDD`).

**30. Export — CSV in v1 for screener, news, portfolio, briefings. Excel via `xlsxwriter` in v1.1.**

**31. Authentication — Single-user local app. No login.**
The app is intended to run on `localhost` for personal use. No auth layer in v1. If exposing externally later, add basic auth via Streamlit config — note in `DECISIONS.md`.

**32. Deployment target — Local first. Provide a Dockerfile in v1.1 for optional cloud deploy.**
v1 must run on the user's laptop with one `streamlit run app.py` command. Dockerfile and `docker-compose.yml` come in v1.1 along with notes on running the briefing scheduler as a separate service.

**33. UI framework — Streamlit. Confirmed for v1.**
Re-evaluate for v2 if the user wants more interactive features (drag-to-rebalance portfolio, advanced charting). Likely v2 candidates: FastAPI + React, or Reflex.

---

## Implementation Sequence (suggested)

The agent should build in this order to keep each milestone shippable:

1. **Scaffold:** `CLAUDE.md` (provided), repo structure, `requirements.txt`, `.env.example`, basic Streamlit shell with the disclaimer footer wired in.
2. **Universe + screener (NSE only first):** `data_sources/universe.py`, `data_sources/prices.py`, `indicators/technical.py`, `screener/runner.py`, single-panel UI showing the ranked table.
3. **Add NYSE + NASDAQ:** extend universe module, validate rate-limit budget.
4. **News panel (one source first — Finnhub):** prove the adapter pattern works, then add MarketAux, then RSS sources.
5. **Portfolio model + manual entry + CSV import.**
6. **Goal tracker + feasibility math.**
7. **Signal engine + position sizing.**
8. **Briefing composer + in-app view.**
9. **Email delivery + APScheduler.**
10. **Hit-rate tracking + 1-year backtest.**
11. **Polish, tests, README, DECISIONS.md updates.**

Ship the dashboard usable at the end of step 4 (screener + news only). Goal tracking + briefing come online by step 9.
