"""CSV / manual portfolio entry.

CSV schema (see README.md):
  ticker,exchange,quantity,avg_cost,purchase_date,currency
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from io import StringIO
from typing import Iterable


@dataclass
class HoldingRow:
    ticker: str
    exchange: str
    quantity: float
    avg_cost: float
    purchase_date: date
    currency: str


REQUIRED_COLUMNS = ("ticker", "exchange", "quantity", "avg_cost", "purchase_date", "currency")


def parse_csv(text: str) -> list[HoldingRow]:
    reader = csv.DictReader(StringIO(text))
    missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames or ())
    if missing:
        raise ValueError(f"Missing CSV columns: {sorted(missing)}")

    rows: list[HoldingRow] = []
    for raw in reader:
        rows.append(
            HoldingRow(
                ticker=raw["ticker"].strip().upper(),
                exchange=raw["exchange"].strip().upper(),
                quantity=float(raw["quantity"]),
                avg_cost=float(raw["avg_cost"]),
                purchase_date=date.fromisoformat(raw["purchase_date"]),
                currency=raw["currency"].strip().upper(),
            )
        )
    return rows


def template_csv() -> str:
    return (
        ",".join(REQUIRED_COLUMNS)
        + "\nAAPL,NASDAQ,10,175.40,2024-08-12,USD"
        + "\nRELIANCE,NSE,25,2840.00,2024-11-04,INR\n"
    )


def to_dicts(rows: Iterable[HoldingRow]) -> list[dict]:
    return [r.__dict__ for r in rows]
