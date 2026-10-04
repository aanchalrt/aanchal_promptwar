"""
Gemini AI service for BlindSpot AI.

Handles the single structured-output call per analysis request.
Supports mock mode (no API key required), a simple LRU cache keyed
by a hash of the normalised input, and a one-retry policy on transient
failures.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from backend.app.config import get_settings
from backend.app.schemas import AnalysisMode, AnalysisResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock response (realistic internship scenario data)
# ---------------------------------------------------------------------------

MOCK_ANALYSIS: dict[str, Any] = {
    "stated_facts": [
        {"text": "The internship is six months long.", "classification": "directly_stated"},
        {"text": "The stipend is described as good.", "classification": "directly_stated"},
        {"text": "The internship location is close to home.", "classification": "directly_stated"},
        {"text": "The role offers industry experience.", "classification": "directly_stated"},
        {"text": "The user has concerns about attendance requirements.", "classification": "directly_stated"},
        {"text": "The user is concerned about exam conflicts.", "classification": "directly_stated"},
        {"text": "The working hours are a concern.", "classification": "directly_stated"},
        {"text": "The user questions whether learning will actually occur.", "classification": "directly_stated"},
        {"text": "The stipend amount relative to cost of living is unspecified.", "classification": "unknown"},
        {"text": "The type of industry experience gained is not detailed.", "classification": "strong_inference"},
    ],
    "priorities": [
        {"factor": "Financial compensation (stipend)", "importance": "high"},
        {"factor": "Proximity to home", "importance": "medium"},
        {"factor": "Industry experience", "importance": "high"},
        {"factor": "Academic continuity (exams, attendance)", "importance": "high"},
        {"factor": "Actual learning quality", "importance": "high"},
        {"factor": "Work-life balance (working hours)", "importance": "medium"},
    ],
    "assumptions": [
        {
            "id": "assumption-1",
            "text": "The stipend is sufficient to justify the time and effort required.",
            "trigger_statement": "good stipend",
            "why_it_matters": "If the stipend does not cover opportunity costs or living expenses, the financial framing of the decision may be incomplete.",
            "what_if_wrong": "The financial benefit could be smaller than anticipated, affecting the overall value assessment.",
            "how_to_verify": "Calculate the monthly stipend against your actual expenses and compare to alternative uses of the same six months.",
            "verification_questions": [
                "What is the exact monthly stipend amount, and how does it compare to your monthly expenses?",
                "Are there additional costs such as commute, meals, or professional attire not accounted for?",
            ],
        },
        {
            "id": "assumption-2",
            "text": "The internship will provide meaningful, transferable industry experience.",
            "trigger_statement": "industry experience",
            "why_it_matters": "The value of the experience depends heavily on the quality and relevance of tasks assigned.",
            "what_if_wrong": "If tasks are routine or unrelated to career goals, the experience may not strengthen the resume or skill set as expected.",
            "how_to_verify": "Ask current or former interns about their day-to-day responsibilities and what skills they developed.",
            "verification_questions": [
                "What specific projects or responsibilities would you be taking on?",
                "Have previous interns in this role been hired full-time or received strong references?",
            ],
        },
        {
            "id": "assumption-3",
            "text": "Attendance and working-hours requirements are compatible with academic obligations.",
            "trigger_statement": "attendance, exams, working hours",
            "why_it_matters": "If the internship schedule conflicts with exams or mandatory attendance requirements, it could affect academic standing.",
            "what_if_wrong": "Academic performance could suffer, potentially affecting GPA, course completion, or standing.",
            "how_to_verify": "Review the internship offer letter for hours and attendance policies, and cross-reference with your academic calendar.",
            "verification_questions": [
                "Does the internship allow time off for exams, or can hours be adjusted during exam periods?",
                "What is the consequence of missing days — is there flexibility or strict attendance enforcement?",
            ],
        },
        {
            "id": "assumption-4",
            "text": "Being close to home is a net positive for this situation.",
            "trigger_statement": "close to home",
            "why_it_matters": "Proximity reduces commute cost and time, but may also reduce exposure to new environments that build independence.",
            "what_if_wrong": "If the reason for wanting to stay close is temporary, it may not be a reliable long-term factor in this decision.",
            "how_to_verify": "Consider whether the proximity matters because of practical constraints, personal preference, or family circumstances.",
            "verification_questions": [
                "Is the proximity a requirement or a preference?",
                "Would a remote or hybrid arrangement satisfy the same underlying need?",
            ],
        },
        {
            "id": "assumption-5",
            "text": "This internship is the best available opportunity in this time window.",
            "trigger_statement": "six-month internship",
            "why_it_matters": "The opportunity cost of committing six months is real; other opportunities may arise or be available now.",
            "what_if_wrong": "A better-aligned opportunity could be missed during this period.",
            "how_to_verify": "Survey other internship or project opportunities available in the same period before committing.",
            "verification_questions": [
                "Have you compared this role to other internships available in the same time frame?",
                "What would you be foregoing by committing to six months?",
            ],
        },
        {
            "id": "assumption-6",
            "text": "Learning will occur passively through exposure to the industry environment.",
            "trigger_statement": "whether I will actually learn",
            "why_it_matters": "Learning in internships often requires proactive effort and a supportive environment; it is rarely guaranteed.",
            "what_if_wrong": "Without structured learning or mentorship, the six months may not add the expected skills or knowledge.",
            "how_to_verify": "Ask about the mentorship structure, learning objectives, and feedback processes during the internship.",
            "verification_questions": [
                "Is there a formal mentorship or onboarding programme?",
                "Are there defined learning goals or projects with feedback built in?",
            ],
        },
    ],
    "blind_spots": [
        {
            "category": "Career alignment",
            "description": "You may want to examine whether the internship domain directly aligns with your intended career path, or whether it builds general experience that may or may not be relevant.",
            "priority": "high",
        },
        {
            "category": "Academic impact",
            "description": "It could be worth exploring how six months away from full-time study might affect graduation timelines or course sequencing.",
            "priority": "high",
        },
        {
            "category": "Network value",
            "description": "One factor that might deserve attention is the professional network the organisation offers and whether connections made during the internship are likely to be valuable.",
            "priority": "medium",
        },
        {
            "category": "Supervisor and team dynamics",
            "description": "You may want to examine the quality of day-to-day supervision, as the learning experience in internships is heavily influenced by direct managers.",
            "priority": "medium",
        },
        {
            "category": "Exit options",
            "description": "It could be worth considering what options exist if the internship proves unsatisfactory midway — whether early termination is possible or carries consequences.",
            "priority": "medium",
        },
        {
            "category": "Reference and credential value",
            "description": "One factor worth investigating is whether this company and role are well-regarded in your target industry, as the signal value of a credential varies significantly.",
            "priority": "low",
        },
    ],
    "tradeoffs": [
        {
            "conflict": "Financial gain vs. academic focus",
            "short_term_benefit": "Earning a stipend and building savings during the internship period.",
            "possible_cost": "Reduced time and energy for coursework, which could affect academic performance.",
            "question": "How much of your academic capacity can you sustainably divert to work without compromising your results?",
        },
        {
            "conflict": "Industry experience now vs. more academic preparation later",
            "short_term_benefit": "Early exposure to professional environments and practical skills.",
            "possible_cost": "Missing advanced coursework or projects that might provide deeper theoretical grounding.",
            "question": "At this stage of your education, which gap — practical experience or theoretical depth — is more important to close?",
        },
        {
            "conflict": "Proximity (comfort) vs. exposure (growth)",
            "short_term_benefit": "Lower stress, lower cost, and familiar surroundings.",
            "possible_cost": "Potentially fewer networking opportunities and less exposure to new professional environments.",
            "question": "Is staying close to home serving a practical need, or could it be limiting the scope of available opportunities?",
        },
        {
            "conflict": "Certainty now vs. better opportunity later",
            "short_term_benefit": "A confirmed offer that removes uncertainty for the next six months.",
            "possible_cost": "Committing early may foreclose other opportunities that emerge in the same window.",
            "question": "How confident are you that this is the best available option relative to what else might be possible?",
        },
    ],
    "success_scenario": {
        "story": "The internship runs smoothly alongside your academic schedule. You are assigned meaningful projects with a supportive mentor, grow your professional network, and receive a strong reference. The stipend covers your expenses and reduces financial pressure, leaving you better positioned for the next stage of your career.",
        "conditions": [
            "The employer accommodates exam schedules with flexibility.",
            "The day-to-day work is aligned with your skill development goals.",
            "A supervisor provides active mentorship and feedback.",
            "The stipend adequately covers your costs.",
            "Academic performance is maintained at a satisfactory level.",
        ],
    },
    "failure_scenario": {
        "story": "The internship working hours conflict with exam preparation, leading to academic stress. The tasks turn out to be routine and do not build meaningful skills. The stipend, once expenses are accounted for, is smaller than expected. By the end of six months, you feel you have missed other opportunities without gaining the experience you had hoped for.",
        "conditions": [
            "Attendance or hours requirements conflict with your exam schedule.",
            "The role involves primarily administrative or repetitive work.",
            "There is no structured mentorship or feedback.",
            "The net financial benefit is lower than anticipated after expenses.",
            "A more aligned opportunity was available but not pursued.",
        ],
    },
    "next_steps": [
        "Request a detailed breakdown of working hours, attendance policy, and exam leave procedures from the employer.",
        "Speak with at least one former intern at this organisation about day-to-day experience and learning quality.",
        "Map the internship timeline against your academic calendar to identify specific conflict points.",
        "Calculate the exact monthly stipend net of all associated costs.",
        "Survey at least two other internship opportunities available in the same time window for comparison.",
    ],
    "disclaimer": "This analysis surfaces information to support your own thinking. It is not a recommendation, decision, or professional advice of any kind.",
}


# ---------------------------------------------------------------------------
# Cache key helper
# ---------------------------------------------------------------------------


def _cache_key(
    *,
    decision: str,
    options: str,
    reasons: str,
    priorities: str,
    constraints: str,
    concerns: str,
    mode: AnalysisMode,
) -> str:
    """
    Compute a stable hash key for the LRU cache.

    Normalises whitespace before hashing so trivially equivalent inputs
    map to the same cache entry.
    """
    normalised = "|".join(
        [
            " ".join(decision.split()),
            " ".join(options.split()),
            " ".join(reasons.split()),
            " ".join(priorities.split()),
            " ".join(constraints.split()),
            " ".join(concerns.split()),
            mode,
        ]
    )
    return hashlib.sha256(normalised.encode()).hexdigest()


# ---------------------------------------------------------------------------
# LRU cache (dict-based so we can parameterise max size)
# ---------------------------------------------------------------------------


class _LRUCache:
    """Simple thread-safe LRU cache with configurable max size."""

    def __init__(self, maxsize: int = 128) -> None:
        self._cache: dict[str, AnalysisResult] = {}
        self._maxsize = maxsize

    def get(self, key: str) -> AnalysisResult | None:
        """Return cached result or None."""
        if key in self._cache:
            self._cache[key] = self._cache.pop(key)  # move to end (LRU)
            return self._cache[key]
        return None

    def set(self, key: str, value: AnalysisResult) -> None:
        """Store result, evicting oldest if at capacity."""
        if key in self._cache:
            self._cache.pop(key)
        elif len(self._cache) >= self._maxsize:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = value


_cache = _LRUCache(maxsize=128)


# ---------------------------------------------------------------------------
# Gemini service
# ---------------------------------------------------------------------------


async def analyse(
    *,
    decision: str,
    options: str,
    reasons: str,
    priorities: str,
    constraints: str,
    concerns: str,
    mode: AnalysisMode,
) -> AnalysisResult:
    """
    Run a single Gemini structured-output call and return a validated AnalysisResult.

    In mock mode, returns a realistic canned response without calling the API.
    Checks an in-memory LRU cache before calling the API.
    Retries once on transient failure, then raises.

    Args:
        decision: The decision under consideration.
        options: Options being weighed.
        reasons: The user's reasoning.
        priorities: What the user values.
        constraints: Practical constraints.
        concerns: Stated concerns.
        mode: Analysis mode — "support", "challenge", or "neutral".

    Returns:
        Validated AnalysisResult.

    Raises:
        RuntimeError: If the Gemini call fails after one retry or JSON is malformed.
    """
    settings = get_settings()

    # -- Mock mode -----------------------------------------------------------
    if settings.mock_mode:
        logger.info("mock_mode=true; returning canned analysis")
        return AnalysisResult.model_validate(MOCK_ANALYSIS)

    # -- Cache check ---------------------------------------------------------
    key = _cache_key(
        decision=decision,
        options=options,
        reasons=reasons,
        priorities=priorities,
        constraints=constraints,
        concerns=concerns,
        mode=mode,
    )
    cached = _cache.get(key)
    if cached is not None:
        logger.info("cache_hit=true")
        return cached

    # -- Build prompt --------------------------------------------------------
    from backend.app.prompts import build_system_prompt, build_user_message  # noqa: F811

    system_prompt = build_system_prompt(mode)
    user_message = build_user_message(
        decision=decision,
        options=options,
        reasons=reasons,
        priorities=priorities,
        constraints=constraints,
        concerns=concerns,
    )

    # -- Gemini call (with one retry) ----------------------------------------
    result = await _call_with_retry(
        system_prompt=system_prompt,
        user_message=user_message,
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )

    _cache.set(key, result)
    return result


async def _call_with_retry(
    *,
    system_prompt: str,
    user_message: str,
    api_key: str,
    model: str,
    timeout: float = 30.0,
) -> AnalysisResult:
    """
    Call the Gemini Interactions API with one retry on transient failure.

    Args:
        system_prompt: The fully-built system prompt.
        user_message: The user's delimited decision context.
        api_key: Gemini API key.
        model: Model identifier.
        timeout: Seconds to wait before timing out.

    Returns:
        Validated AnalysisResult.

    Raises:
        RuntimeError: On unrecoverable failure.
    """
    for attempt in range(2):
        try:
            return await asyncio.wait_for(
                _call_gemini(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    api_key=api_key,
                    model=model,
                ),
                timeout=timeout,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(
                "gemini_call_attempt=%d error_type=%s",
                attempt + 1,
                type(exc).__name__,
            )
            if attempt == 1:
                raise RuntimeError("Gemini call failed after retry.") from exc
    raise RuntimeError("Unreachable")  # pragma: no cover


async def _call_gemini(
    *,
    system_prompt: str,
    user_message: str,
    api_key: str,
    model: str,
) -> AnalysisResult:
    """
    Execute the Gemini structured-output call using the Interactions API.

    Uses response_format with the AnalysisResult JSON schema to enforce
    structured output at the API level.

    Args:
        system_prompt: System instruction for the model.
        user_message: User message containing delimited decision context.
        api_key: Gemini API key.
        model: Model name string.

    Returns:
        Parsed and validated AnalysisResult.

    Raises:
        ValueError: If the returned JSON does not match the schema.
        RuntimeError: If the API call itself fails.
    """
    from google import genai  # type: ignore[import]

    client = genai.Client(api_key=api_key)

    interaction = await asyncio.to_thread(
        client.interactions.create,
        model=model,
        system_instruction=system_prompt,
        input=user_message,
        store=False,
        response_format=[
            {
                "type": "text",
                "mime_type": "application/json",
                "schema": AnalysisResult.model_json_schema(),
            }
        ],
    )

    raw_text = interaction.output_text
    if not raw_text:
        raise RuntimeError("Gemini returned an empty response.")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("gemini_json_parse_error=true")
        raise ValueError("Gemini returned malformed JSON.") from exc

    return AnalysisResult.model_validate(data)
