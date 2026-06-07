POSITIVE_SIGNALS = [
    "stable revenue",
    "positive cash flow",
    "low debt",
    "collateral",
    "profitable",
    "audited financials",
]

NEGATIVE_SIGNALS = [
    "overdue",
    "default",
    "negative cash flow",
    "high debt",
    "litigation",
    "missing financial statements",
    "declining revenue",
]


def calculate_heuristic_score(text: str) -> dict[str, object]:
    normalized = text.lower()
    positives = [signal for signal in POSITIVE_SIGNALS if signal in normalized]
    negatives = [signal for signal in NEGATIVE_SIGNALS if signal in normalized]

    score = 50 + len(positives) * 8 - len(negatives) * 10
    score = max(0, min(100, score))

    if score >= 70:
        risk_level = "Low"
    elif score >= 45:
        risk_level = "Medium"
    else:
        risk_level = "High"

    return {
        "heuristic_score": score,
        "heuristic_risk_level": risk_level,
        "matched_positive_signals": positives,
        "matched_negative_signals": negatives,
    }
