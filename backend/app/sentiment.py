"""Lightweight financial-news sentiment helper using VADER."""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _analyzer():
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        return SentimentIntensityAnalyzer()
    except ImportError:
        return None


def score_sentiment(text: str) -> tuple[str, float]:
    """Return (label, compound score) with a safe lexicon fallback.

    Scores are descriptive text indicators, not investment recommendations.
    """
    text = (text or "").strip()
    analyzer = _analyzer()
    if analyzer is not None:
        compound = float(analyzer.polarity_scores(text).get("compound", 0.0))
    else:
        positives = {"beat", "growth", "gain", "strong", "surge", "profit", "record", "upgrade", "rise", "positive", "improve"}
        negatives = {"miss", "loss", "weak", "fall", "decline", "drop", "risk", "probe", "lawsuit", "negative", "downgrade"}
        words = {w.strip(".,:;!?()[]{}\"' ").lower() for w in text.split()}
        raw = sum(word in positives for word in words) - sum(word in negatives for word in words)
        compound = max(-1.0, min(1.0, raw / max(3.0, len(words) / 4.0)))
    if compound >= 0.05:
        label = "Positive"
    elif compound <= -0.05:
        label = "Negative"
    else:
        label = "Neutral"
    return label, round(compound, 4)
