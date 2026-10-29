from datetime import date, timedelta

from app.analytics import detect_anomalies


def sample_prices(n=45):
    rows = []
    start = date(2025, 1, 1)
    close = 100.0
    for i in range(n):
        close *= 1.001
        rows.append({
            "symbol": "TEST", "date": (start + timedelta(days=i)).isoformat(),
            "open": close * 0.999, "high": close * 1.006, "low": close * 0.994,
            "close": close, "volume": 100_000,
        })
    return rows


def test_detector_returns_empty_for_empty_input():
    assert detect_anomalies([]) == []


def test_detector_flags_a_large_volume_spike():
    rows = sample_prices()
    rows[-1]["volume"] = 900_000
    result = detect_anomalies(rows)
    assert any(item["date"] == rows[-1]["date"] for item in result)


def test_detector_output_has_explanation_fields():
    rows = sample_prices()
    rows[-1]["close"] *= 1.10
    rows[-1]["high"] = rows[-1]["close"] * 1.01
    result = detect_anomalies(rows)
    assert result
    assert {"severity", "reason", "detector", "anomaly_score"}.issubset(result[0])
