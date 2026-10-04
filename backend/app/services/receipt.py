"""
Decision Receipt generator.

Pure function — no I/O, no side effects. Produces a plain-text receipt
that the user can copy or download as a record of their reasoning process.
The receipt ends with a mandatory disclaimer.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.schemas import AnalysisResult, AssumptionLedgerItem, DecisionLog

_STATUS_LABELS: dict[str, str] = {
    "verified": "[✓ Verified]",
    "needs_research": "[? Needs research]",
    "not_important": "[– Not important]",
    "accepted_risk": "[! Accepted risk]",
    "incorrect": "[✗ Incorrect]",
    "unreviewed": "[  Unreviewed]",
}


def _section(title: str, body: str) -> str:
    """Format a named section with a separator line."""
    separator = "─" * 60
    return f"\n{separator}\n{title.upper()}\n{separator}\n{body.strip()}\n"


def generate_receipt(
    *,
    analysis: AnalysisResult,
    ledger: list[AssumptionLedgerItem],
    decision_log: DecisionLog,
) -> str:
    """
    Generate a plain-text Decision Receipt.

    The receipt records the user's reasoning process, assumption review,
    and their own decision. It explicitly states that it is NOT an AI
    recommendation.

    Args:
        analysis: The AnalysisResult produced by the Gemini service.
        ledger: The user's assumption status entries.
        decision_log: The user's own decision record.

    Returns:
        A formatted plain-text string suitable for copy or download.
    """
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        "╔══════════════════════════════════════════════════════════╗",
        "║              BLINDSPOT AI — DECISION RECEIPT             ║",
        "╚══════════════════════════════════════════════════════════╝",
        f"Generated: {now}",
        "",
        "This receipt records the user's reasoning process.",
        "It is NOT an AI recommendation.",
        "BlindSpot AI does not decide for the user.",
        "It makes the user's reasoning visible.",
    ]

    # -- User's decision log -------------------------------------------------
    log_body = "\n".join(
        [
            f"My decision  : {decision_log.my_decision}",
            f"Main reasons : {decision_log.main_reasons or '(not provided)'}",
            f"What could change my mind: {decision_log.what_could_change_my_mind or '(not provided)'}",
            f"Next action  : {decision_log.next_action or '(not provided)'}",
            f"Review date  : {decision_log.review_date or '(not provided)'}",
            f"Confidence   : {decision_log.confidence or '(not provided)'}",
        ]
    )
    lines.append(_section("My Decision (user-written)", log_body))

    # -- Stated facts --------------------------------------------------------
    facts_body = "\n".join(
        f"  [{f.classification}] {f.text}" for f in analysis.stated_facts
    )
    lines.append(_section("Stated Facts Identified", facts_body or "None"))

    # -- Assumptions & ledger ------------------------------------------------
    ledger_by_id = {item.assumption_id: item for item in ledger}
    assumptions_body_parts = []
    for assumption in analysis.assumptions:
        ledger_entry = ledger_by_id.get(assumption.id)
        status_label = (
            _STATUS_LABELS.get(ledger_entry.status, "[  Unreviewed]")
            if ledger_entry
            else "[  Unreviewed]"
        )
        note = f"\n    Note: {ledger_entry.note}" if ledger_entry and ledger_entry.note else ""
        assumptions_body_parts.append(
            f"  {status_label} {assumption.text}\n"
            f"    Trigger: \"{assumption.trigger_statement}\"{note}"
        )
    lines.append(
        _section(
            "Assumption Ledger (user-reviewed)",
            "\n\n".join(assumptions_body_parts) or "No assumptions reviewed.",
        )
    )

    # -- Blind spots ---------------------------------------------------------
    blind_spots_body = "\n".join(
        f"  [{bs.priority.upper()}] {bs.category}: {bs.description}"
        for bs in analysis.blind_spots
    )
    lines.append(_section("Blind Spots Flagged", blind_spots_body or "None"))

    # -- Trade-offs ----------------------------------------------------------
    tradeoffs_body = "\n".join(
        f"  • {t.conflict}\n    Question: {t.question}"
        for t in analysis.tradeoffs
    )
    lines.append(_section("Trade-offs Identified", tradeoffs_body or "None"))

    # -- Suggested next steps ------------------------------------------------
    next_steps_body = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(analysis.next_steps))
    lines.append(_section("Suggested Next Steps", next_steps_body or "None"))

    # -- Footer / mandatory disclaimer ---------------------------------------
    lines.append(
        _section(
            "Important Notice",
            (
                "This receipt records the user's reasoning. It is not an AI recommendation.\n\n"
                f"{analysis.disclaimer}\n\n"
                "BlindSpot AI does not tell you what to decide.\n"
                "It shows you what your decision is built on."
            ),
        )
    )

    return "\n".join(lines)
