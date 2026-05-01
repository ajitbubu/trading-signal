# Investment Decision-Support Dashboard

Personal Streamlit app for screening NSE Nifty 500 / NYSE / NASDAQ equities,
aggregating market news, tracking a portfolio against an annual return goal,
and producing a daily morning briefing.

> **Informational only. Not investment advice. You are responsible for your own trades.**

The full project contract (purpose, architecture, data sources, conventions)
lives in [`CLAUDE.md`](./CLAUDE.md). Non-obvious trade-offs are recorded in
[`DECISIONS.md`](./DECISIONS.md).

---

## Prerequisites

- Python 3.11 or newer
- `pip` and `venv`
- Free API keys (optional, but unlocks more sources):
  - [Finnhub](https://finnhub.io/register) — ticker news + sentiment + analyst data
  - [MarketAux](https://www.marketaux.com/account/dashboard) — India-friendly aggregator
  - [GNews](https://gnews.io/) — backup aggregator
  - [Alpha Vantage](https://www.alphavantage.co/support/#api-key) — sentiment-tagged batch news
- Gmail App Password (or other SMTP) — only required if you want emailed briefings
- An Anthropic API key — only required if you turn on `ENABLE_AI_SUMMARIES=true`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # then fill in keys you have
```

The first run creates `data/app.db` (SQLite) and `briefings/`, `logs/`,
`diskcache/` directories. All four are gitignored.

## Run

```bash
streamlit run app.py
# or
./scripts/run.sh
```

Open `http://localhost:8501`. Override the port with `STREAMLIT_SERVER_PORT`
in `.env`.

## Briefings (manual / cron)

```bash
python -m briefing.run --date today --market nse
python -m briefing.run --date today --market us
```

To schedule briefings outside the app, add cron entries that call those
commands at 08:00 IST and 07:30 ET respectively. The in-app scheduler
(APScheduler) runs them automatically while the Streamlit app is open.

## CSV import (portfolio)

The portfolio page accepts a CSV with this header:

```
ticker,exchange,quantity,avg_cost,purchase_date,currency
```

Example row:

```
AAPL,NASDAQ,10,175.40,2024-08-12,USD
RELIANCE,NSE,25,2840.00,2024-11-04,INR
```

A downloadable template is available from the portfolio page.

## Tests

```bash
pytest -q
```

## Backups

`data/app.db` is the single source of persistent state.

```bash
cp data/app.db data/app.db.bak.$(date +%Y%m%d)
```

## Troubleshooting

- **`yfinance` 429 / empty frames** — the provider rate-limits aggressively.
  Lower `YFINANCE_CONCURRENCY` in `.env` (try `4`). The app already retries
  with exponential backoff.
- **NSE constituent fetch fails** — `nsepython` scrapes nseindia.com which
  occasionally rejects requests. The fetch is cached for 24h, so a transient
  failure is recovered on the next refresh.
- **`USDINR=X` returns null** — log a note in `DECISIONS.md` and switch the
  FX source to `https://api.exchangerate.host/latest?base=USD&symbols=INR`.
- **Streamlit hot-reload picks up `.env` changes too late** — restart the
  app after editing `.env`.

## License

Personal use. No external distribution.
