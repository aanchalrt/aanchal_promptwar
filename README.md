# BlindSpot AI

> **We do not tell you what to decide. We show you what your decision is built on.**

BlindSpot AI is a transparent decision-reasoning assistant that surfaces hidden assumptions, overlooked factors, trade-offs, and unknowns in a user's thinking — without ever recommending a course of action. The user owns their decision; the AI owns only the reflection.

---

## The Problem

When people make decisions, they typically defend a conclusion they have already reached rather than genuinely analysing it. The cognitive blind spots — unstated assumptions, overlooked trade-offs, confirmation bias — remain invisible. Existing AI assistants make this worse by offering recommendations, which bypass the user's thinking rather than strengthening it.

**BlindSpot AI** flips this: it makes the *reasoning itself* visible and testable, then hands control back to the user.

---

## Features

| Feature | Description |
|---|---|
| **Decision intake** | Structured form — decision, options, reasons, priorities, constraints, concerns |
| **Three analysis modes** | Neutral, Support (surface confirming evidence), Challenge (probe weaknesses) |
| **Structured AI analysis** | Stated facts, priorities, assumptions, blind spots, trade-offs, scenarios, verification questions |
| **Evidence-Based Assumption Ledger** | User marks each assumption: Verified / Needs research / Not important / Accepted risk / Incorrect |
| **Reasoning Completeness Score** | 0–100 score updated live from ledger — measures investigation depth, not decision quality |
| **Reasoning chain** | Per-assumption chain: statement → factor → assumption → question |
| **User-Owned Decision Log** | Fields the AI never pre-fills: my decision, reasons, what could change my mind, next action, review date, confidence |
| **Decision Receipt** | Downloadable `.txt` record ending with: "This receipt records the user's reasoning. It is not an AI recommendation." |
| **Demo scenario** | One-click load of the internship example |
| **Privacy controls** | PII detection (email, phone), no server-side storage, privacy notice on every page |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (Vanilla JS ES Module)                                       │
│  index.html + styles.css + app.js (served as static files)           │
│  • textContent only for AI output (XSS prevention)                   │
│  • aria-live, skip link, WCAG AA contrast, focus outlines            │
└──────────────────────┬────────────────────────────────────────────────┘
                       │ HTTPS / fetch()
┌──────────────────────▼────────────────────────────────────────────────┐
│  FastAPI (Python 3.11)  ── Uvicorn                                     │
│  backend/app/main.py                                                   │
│  ├── GET  /api/health                                                  │
│  ├── POST /api/analyze  ← rate limiter, PII detection, sanitisation   │
│  ├── POST /api/score    ← pure function, no AI call                   │
│  └── POST /api/receipt  ← pure function, no AI call                   │
│                                                                        │
│  Security middleware: CSP, X-Frame-Options, X-Content-Type-Options    │
│  In-memory LRU cache keyed by SHA-256(normalised input + mode)        │
└──────────────────────┬────────────────────────────────────────────────┘
                       │ google-genai SDK (single call per analysis)
┌──────────────────────▼────────────────────────────────────────────────┐
│  Google Gemini API (Interactions API, structured output)               │
│  model: gemini-3.8-flash (configurable via GEMINI_MODEL)              │
│  response_format → AnalysisResult.model_json_schema()                 │
│  system_instruction enforces neutrality + prompt-injection defence     │
└──────────────────────────────────────────────────────────────────────┘
         │                              │
┌────────▼──────────┐       ┌───────────▼───────────────────────────┐
│ Google Secret      │       │ Google Cloud Logging                   │
│ Manager            │       │ (structured JSON, no decision text)    │
│ (API key storage)  │       └───────────────────────────────────────┘
└───────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### 1. Clone and set up

```bash
git clone <repo-url> && cd blindspot-ai
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY, or set MOCK_MODE=true for offline use
```

### 3. Run with MOCK_MODE (no API key needed)

```bash
MOCK_MODE=true uvicorn backend.app.main:app --reload --port 8000
# Windows PowerShell:
$env:MOCK_MODE="true"; uvicorn backend.app.main:app --reload --port 8000
```

Open `http://localhost:8000`, click **Load demo scenario**, then **Analyse My Reasoning**.

### 4. Run with a real API key

```bash
GEMINI_API_KEY=your_key_here uvicorn backend.app.main:app --reload --port 8000
```

---

## Running Tests

```bash
# All tests (mock mode is activated inside conftest)
pytest

# With verbose output
pytest -v

# With coverage
pytest --tb=short -q
```

All tests pass without a real Gemini API key.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Gemini API key (required if `MOCK_MODE=false` and no Secret Manager) |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model name |
| `MOCK_MODE` | `false` | Return canned response, no API call |
| `GCP_PROJECT` | — | GCP project ID; enables Secret Manager + Cloud Logging |
| `SECRET_NAME` | — | Secret Manager secret name for the API key |
| `RATE_LIMIT_RPM` | `20` | Max requests per minute per IP on `/api/analyze` |
| `LOG_LEVEL` | `INFO` | Python log level |
| `CACHE_MAX_SIZE` | `128` | LRU cache capacity (entries) |

---

## Cloud Run Deployment

### 1. Set up Secret Manager

```bash
export PROJECT_ID=your-project-id
export SECRET_NAME=gemini-api-key

# Create secret
gcloud secrets create ${SECRET_NAME} \
  --project=${PROJECT_ID} \
  --replication-policy=automatic

# Add your API key
echo -n "YOUR_GEMINI_API_KEY" | \
  gcloud secrets versions add ${SECRET_NAME} \
  --data-file=- \
  --project=${PROJECT_ID}
```

### 2. Build and push

```bash
export REGION=us-central1
export IMAGE=gcr.io/${PROJECT_ID}/blindspot-ai

gcloud builds submit --tag ${IMAGE} --project=${PROJECT_ID}
```

### 3. Deploy to Cloud Run

```bash
gcloud run deploy blindspot-ai \
  --image ${IMAGE} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT=${PROJECT_ID},SECRET_NAME=${SECRET_NAME},GEMINI_MODEL=gemini-3.8-flash,LOG_LEVEL=INFO \
  --service-account blindspot-ai-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 10 \
  --project=${PROJECT_ID}
```

### 4. Grant Secret Manager access

```bash
gcloud secrets add-iam-policy-binding ${SECRET_NAME} \
  --member="serviceAccount:blindspot-ai-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=${PROJECT_ID}
```

---

## Project Structure

```
blindspot-ai/
├── backend/
│   ├── app/
│   │   ├── main.py           FastAPI app, routes, static mount, security headers
│   │   ├── config.py         Settings from env, Secret Manager loading
│   │   ├── schemas.py        All Pydantic v2 models (request/response/Gemini schema)
│   │   ├── prompts.py        System prompt + mode variants + injection defence
│   │   ├── logging_setup.py  Structured logging, Cloud Logging when on GCP
│   │   ├── services/
│   │   │   ├── gemini_service.py  Single Gemini call, LRU cache, mock mode, retry
│   │   │   ├── scoring.py         Reasoning Completeness Score (pure function)
│   │   │   └── receipt.py         Decision Receipt generation (pure function)
│   │   └── security/
│   │       ├── validation.py  Length limits, control-char stripping, sanitisation
│   │       ├── pii.py         Email/phone regex detection
│   │       └── rate_limit.py  Sliding-window per-IP rate limiter
│   └── tests/
│       └── test_main.py      Full pytest suite (12 test classes, 56 tests)
├── frontend/
│   ├── index.html            Semantic HTML, ARIA, skip link, all sections
│   ├── styles.css            WCAG AA, focus outlines, reduced-motion, responsive
│   └── app.js                Vanilla ES module, textContent only for AI output
├── Dockerfile                Cloud Run ready, non-root user
├── requirements.txt
├── pyproject.toml            Ruff linting config + pytest config
├── .env.example              Template — no real secrets
├── .gitignore
└── README.md
```

---

## Evaluation Criteria Mapping

| Criterion | Files / Features |
|---|---|
| **Code Quality** | Type hints throughout; docstrings on all public functions; `ruff` config in `pyproject.toml`; small single-purpose functions; `schemas.py` / `services/` / `security/` separation; no dead code |
| **Security** | API key never in frontend; Secret Manager path in `config.py`; CSP + security headers in `main.py`; input sanitisation in `security/validation.py`; PII detection in `security/pii.py`; rate limiting in `security/rate_limit.py`; prompt-injection defence in `prompts.py`; `textContent` only in `app.js`; no decision data logged or stored |
| **Efficiency** | Exactly one Gemini call per unique analysis; LRU cache in `gemini_service.py`; bounded input/output (Pydantic field limits); one retry only; pure functions for scoring and receipt |
| **Testing** | 56 pytest tests in `backend/tests/test_main.py`; mock mode always on in tests; covers validation, PII, injection, schema, scoring, receipt, rate limiting, health, analyze endpoint, prompt building |
| **Accessibility** | Semantic HTML in `index.html` (header/main/section/h1-h3); skip-to-content link; `aria-live` for loading/errors/score; `fieldset`/`legend` for radio groups; WCAG AA contrast in `styles.css`; visible focus outlines; `prefers-reduced-motion`; no meaning by colour alone (icons + text on every status) |
| **Problem Statement Alignment** | AI never recommends; user-owned Decision Log; Evidence-Based Assumption Ledger; Reasoning Completeness Score; Decision Receipt with mandatory disclaimer; three analysis modes; transparent reasoning chain per assumption |
| **Google Services Usage** | Gemini API (structured output, Interactions API) — `gemini_service.py`; Cloud Run (Dockerfile + deploy commands above); Secret Manager (config.py + setup commands above); Cloud Logging (logging_setup.py) |

---

## Limitations

- **Single-process cache**: The LRU cache is in-memory. On Cloud Run with multiple instances, each has its own cache. For multi-instance caching, Redis or Cloud Memorystore would be needed.
- **No authentication**: Any user can submit analyses. Rate limiting mitigates abuse.
- **PII detection is heuristic**: The regex-based detector may have false positives or negatives.
- **English only**: The system prompt and UI are in English.

---

## Responsible AI

BlindSpot AI is designed around a single principle: **the AI surfaces information; the human makes the decision.**

- The model is explicitly instructed never to recommend a course of action.
- Every assumption is tied to the user's own words, not invented.
- Unknown factors are labelled as unknown.
- Blind spot descriptions use possibility language ("you may want to examine…"), never conclusions ("this will harm you").
- The Decision Receipt ends with: "This receipt records the user's reasoning. It is not an AI recommendation."
- No decision data is stored server-side.
- The Reasoning Completeness Score measures investigation depth only — it does not evaluate the quality of the decision.

---

*BlindSpot AI does not decide for the user. It makes the user's reasoning visible.*
