"""
FastAPI application entry point for BlindSpot AI.

Routes:
    GET  /api/health    — liveness probe
    POST /api/analyze   — structured decision analysis via Gemini
    POST /api/score     — Reasoning Completeness Score
    POST /api/receipt   — Decision Receipt generation

Static frontend files are served from the /frontend directory.
Security headers are applied to every response via middleware.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import get_settings
from backend.app.logging_setup import get_request_id, setup_logging
from backend.app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ErrorResponse,
    HealthResponse,
    ReceiptRequest,
    ReceiptResponse,
    ScoreRequest,
    ScoreResponse,
)
from backend.app.security.pii import contains_pii
from backend.app.security.rate_limit import get_limiter
from backend.app.security.validation import sanitise_field
from backend.app.services.gemini_service import analyse
from backend.app.services.receipt import generate_receipt
from backend.app.services.scoring import compute_score

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("blindspot_ai")

app = FastAPI(
    title="BlindSpot AI",
    description="Transparent decision-reasoning assistant.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
)

# CORS — restrict in production via env
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none';"
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: object) -> Response:
    """
    Inject security headers on every response.

    Applied headers:
    - Content-Security-Policy
    - X-Content-Type-Options
    - X-Frame-Options
    - Referrer-Policy
    - Strict-Transport-Security (recommended for HTTPS deployments)
    """
    start = time.monotonic()
    response: Response = await call_next(request)  # type: ignore[operator]
    latency_ms = round((time.monotonic() - start) * 1000)

    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Request-Latency-Ms"] = str(latency_ms)

    return response


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse, tags=["Meta"])
async def health() -> HealthResponse:
    """Liveness probe — returns ok and current mock_mode status."""
    return HealthResponse(status="ok", mock_mode=settings.mock_mode)


@app.post("/api/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
async def analyze(request: Request, body: AnalyzeRequest) -> AnalyzeResponse:
    """
    Analyse a decision and return a structured AnalysisResult.

    Rate-limited per IP. Sanitises all inputs before processing.
    Detects PII and returns a warning flag (no blocking).
    Exactly one Gemini call is made per non-cached unique input.

    Args:
        request: The FastAPI request (used for IP extraction).
        body: Validated AnalyzeRequest payload.

    Returns:
        AnalyzeResponse with analysis, pii_warning flag, and request_id.

    Raises:
        429: Rate limit exceeded.
        422: Validation error.
        500: Gemini or internal error.
    """
    request_id = get_request_id()
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting
    limiter = get_limiter()
    if not limiter.is_allowed(client_ip):
        logger.warning("rate_limit_exceeded ip=%s request_id=%s", client_ip, request_id)
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(
                error="Too many requests. Please wait a moment before trying again.",
                request_id=request_id,
            ).model_dump(),
        )

    # Sanitise inputs
    decision = sanitise_field(body.decision, 500)
    options = sanitise_field(body.options, 500)
    reasons = sanitise_field(body.reasons, 1000)
    priorities = sanitise_field(body.priorities, 500)
    constraints = sanitise_field(body.constraints, 500)
    concerns = sanitise_field(body.concerns, 500)

    # PII detection (non-blocking)
    combined_text = " ".join([decision, options, reasons, priorities, constraints, concerns])
    pii_warning = contains_pii(combined_text)

    logger.info(
        "analyze_request request_id=%s mode=%s pii_detected=%s",
        request_id,
        body.mode,
        pii_warning,
        # NOTE: decision text is intentionally NOT logged
    )

    try:
        analysis = await analyse(
            decision=decision,
            options=options,
            reasons=reasons,
            priorities=priorities,
            constraints=constraints,
            concerns=concerns,
            mode=body.mode,
        )
    except (ValueError, RuntimeError) as exc:
        logger.error(
            "analyze_error request_id=%s error_type=%s",
            request_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error="Analysis could not be completed. Please try again.",
                request_id=request_id,
            ).model_dump(),
        )

    logger.info("analyze_success request_id=%s", request_id)
    return AnalyzeResponse(
        analysis=analysis,
        pii_warning=pii_warning,
        request_id=request_id,
    )


@app.post("/api/score", response_model=ScoreResponse, tags=["Ledger"])
async def score(body: ScoreRequest) -> ScoreResponse:
    """
    Compute the Reasoning Completeness Score from the user's assumption ledger.

    Args:
        body: ScoreRequest containing ledger items.

    Returns:
        ScoreResponse with numeric score, label, and counts.
    """
    return compute_score(body.ledger)


@app.post("/api/receipt", response_model=ReceiptResponse, tags=["Receipt"])
async def receipt(body: ReceiptRequest) -> ReceiptResponse:
    """
    Generate a plain-text Decision Receipt.

    No data is stored server-side. The receipt is generated on-the-fly from
    the submitted analysis, ledger, and decision log.

    Args:
        body: ReceiptRequest with analysis, ledger, and user decision log.

    Returns:
        ReceiptResponse with the plain-text receipt string.
    """
    text = generate_receipt(
        analysis=body.analysis,
        ledger=body.ledger,
        decision_log=body.decision_log,
    )
    return ReceiptResponse(text=text)


# ---------------------------------------------------------------------------
# Static frontend (served last so API routes take priority)
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"

if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
