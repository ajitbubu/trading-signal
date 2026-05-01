"""Sentiment classifier: provider-supplied first, VADER fallback."""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _vader():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    return SentimentIntensityAnalyzer()


def classify(text: str, provider_label: str | None = None) -> str:
    """Return 'positive' | 'neutral' | 'negative'.

    If the provider already supplied a label we keep it. Otherwise VADER
    on the headline+snippet text.
    """
    if provider_label in {"positive", "neutral", "negative"}:
        return provider_label
    if not text:
        return "neutral"
    score = _vader().polarity_scores(text)["compound"]
    if score >= 0.05:
        return "positive"
    if score <= -0.05:
        return "negative"
    return "neutral"
