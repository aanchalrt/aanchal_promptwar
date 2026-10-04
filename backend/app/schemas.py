"""
Pydantic v2 schemas for BlindSpot AI.

All request/response models are defined here and used for both
API validation and Gemini structured-output enforcement.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enumerations (expressed as Literal types for JSON-schema friendliness)
# ---------------------------------------------------------------------------

FactClassification = Literal["directly_stated", "strong_inference", "unknown"]
ImportanceLevel = Literal["high", "medium", "low"]
AssumptionStatus = Literal[
    "verified",
    "needs_research",
    "not_important",
    "accepted_risk",
    "incorrect",
    "unreviewed",
]
AnalysisMode = Literal["support", "challenge", "neutral"]


# ---------------------------------------------------------------------------
# Sub-models used inside AnalysisResult
# ---------------------------------------------------------------------------


class StatedFact(BaseModel):
    """A fact extracted from the user's decision text."""

    text: str = Field(..., description="The fact as stated or inferred.")
    classification: FactClassification = Field(
        ..., description="How confidently this fact is grounded in the user's input."
    )


class Priority(BaseModel):
    """A factor and its importance in the decision."""

    factor: str = Field(..., description="The factor being weighed.")
    importance: ImportanceLevel = Field(..., description="Relative importance level.")


class Assumption(BaseModel):
    """A hidden or implicit assumption identified in the user's reasoning."""

    id: str = Field(..., description="Short unique slug, e.g. 'assumption-1'.")
    text: str = Field(..., description="The assumption, stated neutrally.")
    trigger_statement: str = Field(
        ...,
        description="Exact quote or close paraphrase from the user's input that surfaces this assumption.",
    )
    why_it_matters: str = Field(
        ..., description="Why this assumption is relevant to the decision."
    )
    what_if_wrong: str = Field(
        ...,
        description="Neutral description of what could change if this assumption is false.",
    )
    how_to_verify: str = Field(
        ..., description="A practical suggestion for checking this assumption."
    )
    verification_questions: list[str] = Field(
        ...,
        min_length=1,
        max_length=4,
        description="Neutral questions the user can ask to investigate this assumption.",
    )


class BlindSpot(BaseModel):
    """A factor or perspective the user may have overlooked."""

    category: str = Field(..., description="Category label, e.g. 'Financial risk'.")
    description: str = Field(
        ...,
        description="Phrased as a possibility, never a conclusion (e.g. 'You may want to examine...').",
    )
    priority: ImportanceLevel = Field(..., description="How important this blind spot may be.")


class Tradeoff(BaseModel):
    """A conflict or tension within the decision space."""

    conflict: str = Field(..., description="The two things in tension.")
    short_term_benefit: str = Field(..., description="Potential short-term gain.")
    possible_cost: str = Field(..., description="Possible longer-term cost.")
    question: str = Field(..., description="A neutral question that highlights the trade-off.")


class Scenario(BaseModel):
    """A plausible success or failure scenario for reflection."""

    story: str = Field(..., description="A brief narrative (2-4 sentences).")
    conditions: list[str] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="Conditions that would need to be true for this scenario.",
    )


# ---------------------------------------------------------------------------
# Top-level analysis result (returned by Gemini, validated, sent to client)
# ---------------------------------------------------------------------------


class AnalysisResult(BaseModel):
    """
    Complete structured analysis of a user's decision and reasoning.

    This is the schema passed to Gemini as response_format and used to
    validate the returned JSON before it is sent to the frontend.
    The AI NEVER recommends a decision; it only surfaces information.
    """

    stated_facts: list[StatedFact] = Field(
        ..., max_length=10, description="Facts extracted from the user's input."
    )
    priorities: list[Priority] = Field(
        ..., max_length=8, description="Factors and their importance."
    )
    assumptions: list[Assumption] = Field(
        ...,
        max_length=6,
        description="Hidden or implicit assumptions in the user's reasoning.",
    )
    blind_spots: list[BlindSpot] = Field(
        ..., max_length=6, description="Overlooked factors or perspectives."
    )
    tradeoffs: list[Tradeoff] = Field(
        ..., max_length=4, description="Tensions or conflicts within the decision."
    )
    success_scenario: Scenario = Field(
        ..., description="A plausible success scenario for reflection."
    )
    failure_scenario: Scenario = Field(
        ..., description="A plausible failure scenario for reflection."
    )
    next_steps: list[str] = Field(
        ...,
        max_length=5,
        description="Suggested investigative or clarifying next steps.",
    )
    disclaimer: str = Field(
        ...,
        description="Mandatory disclaimer reminding the user this is not a recommendation.",
    )

    @field_validator("assumptions")
    @classmethod
    def validate_assumption_ids(cls, assumptions: list[Assumption]) -> list[Assumption]:
        """Ensure assumption IDs are unique."""
        ids = [a.id for a in assumptions]
        if len(ids) != len(set(ids)):
            raise ValueError("Assumption IDs must be unique.")
        return assumptions


# ---------------------------------------------------------------------------
# API request models
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """Request body for POST /api/analyze."""

    decision: str = Field(..., min_length=5, max_length=500)
    options: str = Field(default="", max_length=500)
    reasons: str = Field(..., min_length=5, max_length=1000)
    priorities: str = Field(default="", max_length=500)
    constraints: str = Field(default="", max_length=500)
    concerns: str = Field(default="", max_length=500)
    mode: AnalysisMode = Field(default="neutral")

    @model_validator(mode="after")
    def check_total_length(self) -> "AnalyzeRequest":
        """Guard against unbounded total input."""
        total = (
            len(self.decision)
            + len(self.options)
            + len(self.reasons)
            + len(self.priorities)
            + len(self.constraints)
            + len(self.concerns)
        )
        if total > 3000:
            raise ValueError("Total input length exceeds the 3 000-character limit.")
        return self


class AssumptionLedgerItem(BaseModel):
    """A single reviewed assumption entry in the user's ledger."""

    assumption_id: str = Field(..., min_length=1, max_length=50)
    status: AssumptionStatus = Field(...)
    note: str = Field(default="", max_length=500)


class ScoreRequest(BaseModel):
    """Request body for POST /api/score."""

    ledger: list[AssumptionLedgerItem] = Field(..., max_length=6)


class DecisionLog(BaseModel):
    """The user's own decision record — never pre-filled by the AI."""

    my_decision: str = Field(..., min_length=1, max_length=500)
    main_reasons: str = Field(default="", max_length=500)
    what_could_change_my_mind: str = Field(default="", max_length=500)
    next_action: str = Field(default="", max_length=300)
    review_date: str = Field(default="", max_length=50)
    confidence: str = Field(default="", max_length=100)


class ReceiptRequest(BaseModel):
    """Request body for POST /api/receipt."""

    analysis: AnalysisResult
    ledger: list[AssumptionLedgerItem] = Field(default_factory=list, max_length=6)
    decision_log: DecisionLog


# ---------------------------------------------------------------------------
# API response models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response for GET /api/health."""

    status: str = "ok"
    mock_mode: bool = False


class AnalyzeResponse(BaseModel):
    """Wrapped analysis result with metadata."""

    analysis: AnalysisResult
    pii_warning: bool = False
    request_id: str


class ScoreResponse(BaseModel):
    """Reasoning completeness score response."""

    score: int = Field(..., ge=0, le=100)
    label: str
    verified: int
    unverified: int
    total: int


class ReceiptResponse(BaseModel):
    """Plain-text decision receipt."""

    text: str


class ErrorResponse(BaseModel):
    """Generic safe error response."""

    error: str
    request_id: str
