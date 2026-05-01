"""Tests for the auto-detecting CSV importer.

Covers canonical schema + Fidelity export. Fidelity edge cases:
  - BOM-prefixed header
  - $/comma/percent stripping
  - blank-quantity rows (cash money market)
  - `**` / `***` symbol suffixes
  - trailing disclaimer rows (no Symbol)
  - `--` placeholder for percent-of-account on cash rows
"""
from __future__ import annotations

from datetime import date

import pytest

from portfolio.importer import HoldingRow, parse_canonical, parse_csv, parse_fidelity


CANONICAL_OK = """ticker,exchange,quantity,avg_cost,purchase_date,currency
AAPL,NASDAQ,10,175.40,2024-08-12,USD
RELIANCE,NSE,25,2840.00,2024-11-04,INR
"""


FIDELITY_SAMPLE = """﻿Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type
Z1,Individual,FZFXX**,HELD IN MONEY MARKET,,,,$1000.00,,,,,5.00%,,,Cash,
Z1,Individual,NVDA,NVIDIA CORPORATION COM,100,$200.00,+$1.00,$20000.00,+$100.00,+0.50%,+$5000.00,+33.33%,40.00%,$15000.00,$150.00,Cash,
Z1,Individual,AAPL,APPLE INC,4,$281.82,+$10.47,$1127.28,+$41.88,+3.85%,+$192.36,+20.57%,2.00%,$934.92,"$233.73",Cash,
Z1,Individual,USD***,US DOLLARS,,,,$0.00,,,,,--,,,Cash,

"The data and information in this spreadsheet is provided to you solely for your use and is not for distribution."
"""


def test_canonical_happy_path():
    rows = parse_canonical(CANONICAL_OK)
    assert len(rows) == 2
    assert rows[0] == HoldingRow("AAPL", "NASDAQ", 10.0, 175.40, date(2024, 8, 12), "USD")
    assert rows[1] == HoldingRow("RELIANCE", "NSE", 25.0, 2840.00, date(2024, 11, 4), "INR")


def test_canonical_missing_columns_raises():
    with pytest.raises(ValueError):
        parse_canonical("ticker,exchange,quantity\nAAPL,NASDAQ,10\n")


def test_fidelity_happy_path_strips_currency_strings():
    today = date(2026, 5, 1)
    rows = parse_fidelity(FIDELITY_SAMPLE, today=today)
    tickers = [r.ticker for r in rows]
    assert tickers == ["NVDA", "AAPL"]
    nvda = rows[0]
    assert nvda.quantity == 100.0
    assert nvda.avg_cost == 150.00
    assert nvda.exchange == "US"
    assert nvda.currency == "USD"
    assert nvda.purchase_date == date(2026, 1, 1)


def test_fidelity_skips_cash_rows():
    rows = parse_fidelity(FIDELITY_SAMPLE)
    assert all(not r.ticker.endswith("*") for r in rows)
    assert "FZFXX" not in [r.ticker for r in rows]
    assert "USD" not in [r.ticker for r in rows]


def test_fidelity_skips_trailing_disclaimer_rows():
    rows = parse_fidelity(FIDELITY_SAMPLE)
    assert all(r.ticker.isalnum() or "-" in r.ticker for r in rows)
    assert len(rows) == 2


def test_fidelity_handles_quoted_avg_cost():
    rows = parse_fidelity(FIDELITY_SAMPLE)
    aapl = next(r for r in rows if r.ticker == "AAPL")
    assert aapl.avg_cost == 233.73


def test_auto_detect_canonical():
    rows = parse_csv(CANONICAL_OK)
    assert len(rows) == 2 and rows[0].ticker == "AAPL"


def test_auto_detect_fidelity():
    rows = parse_csv(FIDELITY_SAMPLE, today=date(2026, 5, 1))
    assert {r.ticker for r in rows} == {"NVDA", "AAPL"}


def test_auto_detect_unknown_header_raises():
    with pytest.raises(ValueError, match="Unrecognized CSV header"):
        parse_csv("foo,bar,baz\n1,2,3\n")
