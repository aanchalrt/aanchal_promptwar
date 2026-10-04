"""
Reasoning Completeness Score calculator.

Pure function — no I/O, no side effects. Computes a 0–100 score based on
the statuses the user has assigned to each assumption in their ledger.
"""

from __future__ import annotations

from backend.app.schemas import AssumptionLedgerItem, ScoreResponse

# Weight assigned to each assumption status
_STATUS_WEIGHTS: dict[str, int] = {
    "verified": 100,
    "needs_research": 30,
    "not_important": 70,  # deliberate dismissal is still a considered action
    "accepted_risk": 60,  # aware of the risk, chose to proceed
    "incorrect": 50,  # user rejected the assumption — that's still engagement
    "unreviewed": 0,
}

# Labels for score bands
_SCORE_LABELS: list[tuple[int, str]] = [
    (90, "Highly thorough"),
    (70, "Well investigated"),
    (50, "Partially investigated"),
    (30, "Preliminary review"),
    (0, "Investigation not started"),
]


def compute_score(ledger: list[AssumptionLedgerItem]) -> ScoreResponse:
    """
    Calculate the Reasoning Completeness Score from the user's assumption ledger.

    The score reflects how thoroughly the user has engaged with each flagged
    assumption. It does NOT indicate whether the decision itself is correct.

    Args:
        ledger: List of assumption items with their review statuses.

    Returns:
        ScoreResponse with numeric score (0–100), label, and counts.
    """
    if not ledger:
        return ScoreResponse(
            score=0,
            label="Investigation not started",
            verified=0,
            unverified=0,
            total=0,
        )

    total = len(ledger)
    weights = [_STATUS_WEIGHTS.get(item.status, 0) for item in ledger]
    raw_score = sum(weights) / total  # average weight

    # Round to nearest integer, clamp to [0, 100]
    score = max(0, min(100, round(raw_score)))

    # Determine label
    label = _SCORE_LABELS[-1][1]
    for threshold, text in _SCORE_LABELS:
        if score >= threshold:
            label = text
            break

    verified = sum(
        1 for item in ledger if item.status in {"verified", "not_important"}
    )
    unverified = total - verified

    return ScoreResponse(
        score=score,
        label=label,
        verified=verified,
        unverified=unverified,
        total=total,
    )
