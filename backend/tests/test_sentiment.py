from app.sentiment import score_sentiment


def test_sentiment_returns_valid_label_and_score():
    label, score = score_sentiment("The company reported strong growth and record profits.")
    assert label in {"Positive", "Neutral", "Negative"}
    assert -1.0 <= score <= 1.0


def test_empty_sentiment_is_safe():
    label, score = score_sentiment("")
    assert label == "Neutral"
    assert -1.0 <= score <= 1.0
