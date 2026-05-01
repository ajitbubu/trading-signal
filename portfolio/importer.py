"""CSV / manual portfolio entry.

Two formats are accepted, auto-detected by header signature:

  - **Canonical** (documented in README.md):
      ticker,exchange,quantity,avg_cost,purchase_date,currency

  - **Fidelity export** (matches `Portfolio_Positions_*.csv` from
    Fidelity's web download):
      Account Number, Account Name, Symbol, Description, Quantity,
      Last Price, ..., Average Cost Basis, Type, ...

Fidelity exports omit `purchase_date` — we default to Jan 1 of the
current year (matches the goal-tracker's start_date convention; see
DECISIONS.md D-012). Cash / money-market positions (symbols suffixed
with `**` or `***`) and the trailing disclaimer rows are skipped.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from io import StringIO
from typing import Iterable

import structlog

log = structlog.get_logger(__name__)

CANONICAL_COLUMNS = ("ticker", "exchange", "quantity", "avg_cost", "purchase_date", "currency")
FIDELITY_HEADER_MARKERS = ("Symbol", "Average Cost Basis")


@dataclass
class HoldingRow:
    ticker: str
    exchange: str
    quantity: float
    avg_cost: float
    purchase_date: date
    currency: str


def _strip_money(value: str) -> float:
    """Convert "$201.7601" / "+1.09%" / "-$2,336.63" to a float."""
    if value is None:
        return 0.0
    cleaned = value.replace("$", "").replace(",", "").replace("%", "").replace("+", "").strip()
    if not cleaned or cleaned == "--":
        return 0.0
    return float(cleaned)


def _is_cash_symbol(symbol: str) -> bool:
    return symbol.endswith("**") or symbol.endswith("***")


def _detect_format(text: str) -> str:
    """Return 'canonical' | 'fidelity'. Raises ValueError if neither."""
    stripped = text.lstrip("﻿")
    first_line = stripped.splitlines()[0] if stripped else ""
    cols = [c.strip() for c in first_line.split(",")]
    cols_set = set(cols)
    if set(CANONICAL_COLUMNS).issubset(cols_set):
        return "canonical"
    if all(marker in cols_set for marker in FIDELITY_HEADER_MARKERS):
        return "fidelity"
    raise ValueError(
        f"Unrecognized CSV header. Need either canonical schema "
        f"{CANONICAL_COLUMNS} or Fidelity export with "
        f"{FIDELITY_HEADER_MARKERS}. Got: {cols}"
    )


def parse_canonical(text: str) -> list[HoldingRow]:
    text = text.lstrip("﻿")
    reader = csv.DictReader(StringIO(text))
    missing = set(CANONICAL_COLUMNS) - set(reader.fieldnames or ())
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


def parse_fidelity(text: str, *, today: date | None = None) -> list[HoldingRow]:
    """Parse a Fidelity Portfolio_Positions export.

    Skipped rows:
      - blank Symbol or blank Quantity (cash money market lines)
      - Symbol ending in `**` or `***` (cash markers)
      - rows where Quantity isn't numeric (trailing disclaimer text)
    """
    today = today or date.today()
    default_purchase_date = date(today.year, 1, 1)

    text = text.lstrip("﻿")
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError("Empty CSV")

    # Fidelity sometimes pads header column names with surrounding whitespace.
    fieldnames_normalized = {name: name.strip() for name in reader.fieldnames}
    needed = {"Symbol", "Quantity", "Average Cost Basis"}
    if not needed.issubset(set(fieldnames_normalized.values())):
        raise ValueError(f"Fidelity CSV missing required columns: {needed}")

    rows: list[HoldingRow] = []
    skipped_cash = 0
    skipped_disclaimer = 0
    skipped_no_quantity = 0

    for raw in reader:
        # The disclaimer text rows after the data have one column with a long
        # quoted string and no Symbol field; csv.DictReader leaves them as
        # `{None: [text]}` or a Symbol that's literally the start of a sentence.
        symbol = (raw.get("Symbol") or "").strip()
        quantity_raw = (raw.get("Quantity") or "").strip()
        if not symbol:
            skipped_disclaimer += 1
            continue
        if _is_cash_symbol(symbol):
            skipped_cash += 1
            continue
        if not quantity_raw:
            skipped_no_quantity += 1
            continue
        try:
            quantity = _strip_money(quantity_raw)
        except ValueError:
            skipped_disclaimer += 1
            continue
        if quantity <= 0:
            skipped_no_quantity += 1
            continue

        avg_cost_raw = (raw.get("Average Cost Basis") or "").strip()
        try:
            avg_cost = _strip_money(avg_cost_raw)
        except ValueError:
            avg_cost = 0.0

        rows.append(
            HoldingRow(
                ticker=symbol.upper(),
                exchange="US",
                quantity=quantity,
                avg_cost=avg_cost,
                purchase_date=default_purchase_date,
                currency="USD",
            )
        )

    log.info(
        "fidelity_csv_parsed",
        rows=len(rows),
        skipped_cash=skipped_cash,
        skipped_disclaimer=skipped_disclaimer,
        skipped_no_quantity=skipped_no_quantity,
    )
    return rows


def parse_csv(text: str, *, today: date | None = None) -> list[HoldingRow]:
    """Auto-detect canonical vs Fidelity and parse accordingly."""
    fmt = _detect_format(text)
    if fmt == "canonical":
        return parse_canonical(text)
    return parse_fidelity(text, today=today)


def template_csv() -> str:
    """Return the canonical-schema template a user can download."""
    return (
        ",".join(CANONICAL_COLUMNS)
        + "\nAAPL,NASDAQ,10,175.40,2024-08-12,USD"
        + "\nRELIANCE,NSE,25,2840.00,2024-11-04,INR\n"
    )


def to_dicts(rows: Iterable[HoldingRow]) -> list[dict]:
    return [r.__dict__ for r in rows]
