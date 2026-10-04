/**
 * BlindSpot AI — Frontend Application
 *
 * Vanilla JS ES module. No build step, no frameworks.
 * All AI output is rendered via textContent, never innerHTML, to prevent XSS.
 * Communicates with the FastAPI backend over fetch.
 */

"use strict";

// ─── Constants ───────────────────────────────────────────────────────────────

const API_BASE = "";  // Same origin — backend serves frontend

/** Demo scenario: six-month internship */
const DEMO_SCENARIO = {
  decision: "Whether to accept a six-month paid internship at a local tech company",
  options: "Accept the offer, decline the offer, or try to negotiate part-time or later start date",
  reasons: "The stipend is good, the company is close to home, and I will gain real industry experience in a field related to my degree",
  priorities: "Learning relevant skills, maintaining academic performance, earning income",
  constraints: "Must attend university during the internship period and sit exams in November",
  concerns: "Strict attendance policy may conflict with classes, the working hours are long, exams could suffer, and I am not sure whether I will actually learn meaningful skills or just do routine tasks",
  mode: "neutral",
};

/** Status display config — text + icon, never colour alone */
const STATUS_CONFIG = {
  verified:       { label: "Verified",       icon: "✓", cssClass: "selected-verified" },
  needs_research: { label: "Needs research", icon: "?", cssClass: "selected-needs_research" },
  not_important:  { label: "Not important",  icon: "–", cssClass: "selected-not_important" },
  accepted_risk:  { label: "Accepted risk",  icon: "!", cssClass: "selected-accepted_risk" },
  incorrect:      { label: "Incorrect",      icon: "✗", cssClass: "selected-incorrect" },
};

// ─── State ───────────────────────────────────────────────────────────────────

/** @type {object|null} Current analysis result from the API */
let currentAnalysis = null;

/** @type {Map<string, {status: string, note: string}>} Ledger state keyed by assumption ID */
const ledgerState = new Map();

// ─── DOM Helpers ─────────────────────────────────────────────────────────────

/**
 * Get a DOM element by ID, throwing if not found.
 * @param {string} id
 * @returns {HTMLElement}
 */
function el(id) {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Element #${id} not found`);
  return element;
}

/**
 * Show an element by removing the "hidden" class.
 * @param {HTMLElement} element
 */
function show(element) {
  element.classList.remove("hidden");
}

/**
 * Hide an element by adding the "hidden" class.
 * @param {HTMLElement} element
 */
function hide(element) {
  element.classList.add("hidden");
}

/**
 * Safely set text content on an element.
 * NEVER uses innerHTML — all AI content goes through textContent.
 * @param {HTMLElement} element
 * @param {string} text
 */
function setText(element, text) {
  element.textContent = text;
}

/**
 * Create an element with optional class names and text content.
 * @param {string} tag
 * @param {object} opts
 * @returns {HTMLElement}
 */
function createElement(tag, { classes = [], text = "", attrs = {} } = {}) {
  const elem = document.createElement(tag);
  if (classes.length) elem.className = classes.join(" ");
  if (text) elem.textContent = text;
  for (const [k, v] of Object.entries(attrs)) elem.setAttribute(k, v);
  return elem;
}

// ─── Character Counters ───────────────────────────────────────────────────────

/**
 * Attach a live character counter to a textarea or input.
 * @param {string} fieldId
 * @param {string} counterId
 * @param {number} max
 */
function attachCounter(fieldId, counterId, max) {
  const field = document.getElementById(fieldId);
  const counter = document.getElementById(counterId);
  if (!field || !counter) return;

  const update = () => {
    const len = field.value.length;
    setText(counter, `${len} / ${max}`);
    counter.classList.remove("near-limit", "at-limit");
    if (len >= max) counter.classList.add("at-limit");
    else if (len >= max * 0.85) counter.classList.add("near-limit");
  };

  field.addEventListener("input", update);
  update();
}

// ─── Demo Loader ─────────────────────────────────────────────────────────────

/**
 * Fill the intake form with the demo internship scenario.
 */
function loadDemo() {
  const fields = {
    "decision-field":     DEMO_SCENARIO.decision,
    "options-field":      DEMO_SCENARIO.options,
    "reasons-field":      DEMO_SCENARIO.reasons,
    "priorities-field":   DEMO_SCENARIO.priorities,
    "constraints-field":  DEMO_SCENARIO.constraints,
    "concerns-field":     DEMO_SCENARIO.concerns,
  };

  for (const [id, value] of Object.entries(fields)) {
    const field = document.getElementById(id);
    if (field) {
      field.value = value;
      field.dispatchEvent(new Event("input"));
    }
  }

  // Set mode to neutral
  const neutralRadio = document.querySelector('input[name="mode"][value="neutral"]');
  if (neutralRadio) neutralRadio.checked = true;

  // Announce to screen readers
  announceToScreenReader("Demo scenario loaded. Review the fields and click Analyse My Reasoning.");
}

// ─── Screen Reader Announcements ─────────────────────────────────────────────

/**
 * Announce a message to screen readers via an aria-live region.
 * @param {string} message
 */
function announceToScreenReader(message) {
  let announcer = document.getElementById("sr-announcer");
  if (!announcer) {
    announcer = document.createElement("div");
    announcer.id = "sr-announcer";
    announcer.setAttribute("aria-live", "polite");
    announcer.setAttribute("aria-atomic", "true");
    announcer.className = "sr-only";
    announcer.style.cssText = "position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden;";
    document.body.appendChild(announcer);
  }
  announcer.textContent = "";
  requestAnimationFrame(() => { announcer.textContent = message; });
}

// ─── Form Submission ──────────────────────────────────────────────────────────

/**
 * Handle the intake form submission.
 * @param {SubmitEvent} event
 */
async function handleFormSubmit(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const errorEl = el("form-error");
  hide(errorEl);

  // Collect field values
  const decision    = el("decision-field").value.trim();
  const options     = el("options-field").value.trim();
  const reasons     = el("reasons-field").value.trim();
  const priorities  = el("priorities-field").value.trim();
  const constraints = el("constraints-field").value.trim();
  const concerns    = el("concerns-field").value.trim();
  const mode        = form.querySelector('input[name="mode"]:checked')?.value ?? "neutral";

  // Client-side validation
  const errors = [];
  if (!decision || decision.length < 5) errors.push("Please describe your decision (at least 5 characters).");
  if (!reasons  || reasons.length  < 5) errors.push("Please provide your reasons (at least 5 characters).");

  if (errors.length > 0) {
    show(errorEl);
    setText(errorEl, errors.join(" "));
    errorEl.focus();
    return;
  }

  // Show loading state
  hide(el("intake-section"));
  hide(el("results-section"));
  show(el("loading-indicator"));
  announceToScreenReader("Analysing your reasoning. This may take a moment.");

  try {
    const response = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, options, reasons, priorities, constraints, concerns, mode }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error ?? "An unexpected error occurred.");
    }

    // Handle PII warning
    const piiWarning = el("pii-warning");
    if (data.pii_warning) {
      show(piiWarning);
    } else {
      hide(piiWarning);
    }

    currentAnalysis = data.analysis;
    ledgerState.clear();
    for (const assumption of currentAnalysis.assumptions) {
      ledgerState.set(assumption.id, { status: "unreviewed", note: "" });
    }

    renderResults(currentAnalysis);
    hide(el("loading-indicator"));
    show(el("results-section"));
    el("results-section").scrollIntoView({ behavior: "smooth", block: "start" });
    announceToScreenReader("Analysis complete. Results are now visible below.");

  } catch (err) {
    hide(el("loading-indicator"));
    show(el("intake-section"));
    show(errorEl);
    setText(errorEl, err.message ?? "An error occurred. Please try again.");
    errorEl.focus();
    announceToScreenReader("Error: " + (err.message ?? "An error occurred."));
  }
}

// ─── Results Rendering ───────────────────────────────────────────────────────

/**
 * Render all analysis result sections.
 * @param {object} analysis - AnalysisResult from the API
 */
function renderResults(analysis) {
  renderDisclaimer(analysis.disclaimer);
  renderStatedFacts(analysis.stated_facts);
  renderPriorities(analysis.priorities);
  renderBlindSpots(analysis.blind_spots);
  renderTradeoffs(analysis.tradeoffs);
  renderScenarios(analysis.success_scenario, analysis.failure_scenario);
  renderVerificationQuestions(analysis.assumptions);
  renderAssumptionLedger(analysis.assumptions);
  updateScore();
}

/** Render the disclaimer text. */
function renderDisclaimer(disclaimer) {
  setText(el("analysis-disclaimer"), disclaimer);
}

/** Render stated facts list. */
function renderStatedFacts(facts) {
  const list = el("stated-facts-list");
  list.innerHTML = "";

  const classificationMeta = {
    directly_stated: { text: "Directly stated",  icon: "◉" },
    strong_inference: { text: "Strong inference", icon: "◈" },
    unknown:          { text: "Unknown",           icon: "◇" },
  };

  for (const fact of facts) {
    const li = createElement("li", { classes: ["fact-item"] });

    const meta = classificationMeta[fact.classification] ?? classificationMeta.unknown;
    const badge = createElement("span", {
      classes: ["fact-badge", `fact-badge--${fact.classification}`],
    });
    badge.textContent = `${meta.icon} ${meta.text}`;
    badge.setAttribute("aria-label", meta.text);

    const text = createElement("span");
    text.textContent = fact.text;

    li.appendChild(badge);
    li.appendChild(text);
    list.appendChild(li);
  }
}

/** Render priorities list. */
function renderPriorities(priorities) {
  const list = el("priorities-list");
  list.innerHTML = "";

  const importanceMeta = {
    high:   { text: "High",   icon: "▲" },
    medium: { text: "Medium", icon: "◆" },
    low:    { text: "Low",    icon: "▽" },
  };

  for (const priority of priorities) {
    const li = createElement("li", { classes: ["priority-item"] });

    const factorSpan = createElement("span");
    factorSpan.textContent = priority.factor;

    const meta = importanceMeta[priority.importance] ?? importanceMeta.low;
    const badge = createElement("span", {
      classes: ["priority-badge", `priority-badge--${priority.importance}`],
    });
    badge.textContent = `${meta.icon} ${meta.text}`;
    badge.setAttribute("aria-label", `Importance: ${meta.text}`);

    li.appendChild(factorSpan);
    li.appendChild(badge);
    list.appendChild(li);
  }
}

/** Render blind spots with dismiss controls. */
function renderBlindSpots(blindSpots) {
  const list = el("blind-spots-list");
  list.innerHTML = "";

  const priorityMeta = { high: "High", medium: "Medium", low: "Low" };

  for (const spot of blindSpots) {
    const li = createElement("li", { classes: ["insight-item"] });

    const header = createElement("div", { classes: ["insight-header"] });

    const category = createElement("span", { classes: ["insight-category"] });
    category.textContent = spot.category;

    const priorityBadge = createElement("span", {
      classes: ["insight-priority-badge", `insight-priority-badge--${spot.priority}`],
    });
    priorityBadge.textContent = priorityMeta[spot.priority] ?? spot.priority;
    priorityBadge.setAttribute("aria-label", `Priority: ${priorityMeta[spot.priority] ?? spot.priority}`);

    const dismissBtn = createElement("button", { classes: ["dismiss-btn"] });
    dismissBtn.textContent = "Dismiss";
    dismissBtn.setAttribute("aria-label", `Dismiss blind spot: ${spot.category}`);
    dismissBtn.setAttribute("type", "button");
    dismissBtn.addEventListener("click", () => {
      li.remove();
      announceToScreenReader(`Blind spot "${spot.category}" dismissed.`);
    });

    header.appendChild(category);
    header.appendChild(priorityBadge);
    header.appendChild(dismissBtn);

    const description = createElement("p");
    description.textContent = spot.description;

    li.appendChild(header);
    li.appendChild(description);
    list.appendChild(li);
  }
}

/** Render trade-offs. */
function renderTradeoffs(tradeoffs) {
  const list = el("tradeoffs-list");
  list.innerHTML = "";

  for (const tradeoff of tradeoffs) {
    const li = createElement("li", { classes: ["tradeoff-item"] });

    const conflict = createElement("div", { classes: ["tradeoff-conflict"] });
    conflict.textContent = tradeoff.conflict;

    const grid = createElement("div", { classes: ["tradeoff-grid"] });

    const benefitCol = createElement("div", { classes: ["tradeoff-col"] });
    const benefitLabel = createElement("label");
    benefitLabel.textContent = "Short-term benefit";
    const benefitText = createElement("p");
    benefitText.textContent = tradeoff.short_term_benefit;
    benefitCol.appendChild(benefitLabel);
    benefitCol.appendChild(benefitText);

    const costCol = createElement("div", { classes: ["tradeoff-col"] });
    const costLabel = createElement("label");
    costLabel.textContent = "Possible cost";
    const costText = createElement("p");
    costText.textContent = tradeoff.possible_cost;
    costCol.appendChild(costLabel);
    costCol.appendChild(costText);

    grid.appendChild(benefitCol);
    grid.appendChild(costCol);

    const question = createElement("p", { classes: ["tradeoff-question"] });
    question.textContent = `"${tradeoff.question}"`;

    li.appendChild(conflict);
    li.appendChild(grid);
    li.appendChild(question);
    list.appendChild(li);
  }
}

/** Render success/failure scenarios. */
function renderScenarios(successScenario, failureScenario) {
  setText(el("success-story"), successScenario.story);
  setText(el("failure-story"), failureScenario.story);

  const renderConditions = (listId, conditions) => {
    const list = el(listId);
    list.innerHTML = "";
    for (const cond of conditions) {
      const li = createElement("li");
      li.textContent = cond;
      list.appendChild(li);
    }
  };

  renderConditions("success-conditions", successScenario.conditions);
  renderConditions("failure-conditions", failureScenario.conditions);
}

/** Collect and render all verification questions from assumptions. */
function renderVerificationQuestions(assumptions) {
  const list = el("verification-list");
  list.innerHTML = "";

  for (const assumption of assumptions) {
    for (const question of assumption.verification_questions) {
      const li = createElement("li", { classes: ["verification-item"] });
      li.textContent = question;
      list.appendChild(li);
    }
  }
}

// ─── Assumption Ledger ───────────────────────────────────────────────────────

/**
 * Render the assumption ledger with cards, status radios, and notes.
 * @param {Array} assumptions
 */
function renderAssumptionLedger(assumptions) {
  const container = el("assumption-ledger");
  container.innerHTML = "";

  for (const assumption of assumptions) {
    const card = buildAssumptionCard(assumption);
    container.appendChild(card);
  }
}

/**
 * Build an assumption card element.
 * @param {object} assumption
 * @returns {HTMLElement}
 */
function buildAssumptionCard(assumption) {
  const card = createElement("div", { classes: ["assumption-card"] });
  card.setAttribute("data-assumption-id", assumption.id);

  // ── Header ──
  const header = createElement("div", { classes: ["assumption-card-header"] });

  const headerLeft = createElement("div");
  const idEl = createElement("div", { classes: ["assumption-card-id"] });
  idEl.textContent = assumption.id;
  const textEl = createElement("div", { classes: ["assumption-card-text"] });
  textEl.textContent = assumption.text;
  const triggerEl = createElement("div", { classes: ["assumption-card-trigger"] });
  triggerEl.textContent = `Trigger: "${assumption.trigger_statement}"`;

  headerLeft.appendChild(idEl);
  headerLeft.appendChild(textEl);
  headerLeft.appendChild(triggerEl);

  // Dismiss button
  const dismissBtn = createElement("button", { classes: ["dismiss-btn"] });
  dismissBtn.textContent = "Dismiss";
  dismissBtn.setAttribute("type", "button");
  dismissBtn.setAttribute("aria-label", `Dismiss assumption: ${assumption.text}`);
  dismissBtn.addEventListener("click", () => {
    card.remove();
    ledgerState.delete(assumption.id);
    updateScore();
    announceToScreenReader(`Assumption "${assumption.id}" dismissed.`);
  });

  header.appendChild(headerLeft);
  header.appendChild(dismissBtn);

  // ── Body ──
  const body = createElement("div", { classes: ["assumption-card-body"] });

  // Detail rows
  const details = [
    { label: "Why it matters",  value: assumption.why_it_matters  },
    { label: "What if wrong",   value: assumption.what_if_wrong   },
    { label: "How to verify",   value: assumption.how_to_verify   },
  ];
  for (const detail of details) {
    const row = createElement("div", { classes: ["assumption-detail"] });
    const labelEl = createElement("span", { classes: ["assumption-detail-label"] });
    labelEl.textContent = detail.label;
    const valueEl = createElement("span");
    valueEl.textContent = detail.value;
    row.appendChild(labelEl);
    row.appendChild(valueEl);
    body.appendChild(row);
  }

  // ── Collapsible "Why was this flagged?" reasoning chain ──
  const whyBtn = createElement("button", { classes: ["why-flagged-toggle"] });
  whyBtn.textContent = "▶ Why was this flagged?";
  whyBtn.setAttribute("type", "button");
  whyBtn.setAttribute("aria-expanded", "false");
  const whyContentId = `why-${assumption.id}`;
  whyBtn.setAttribute("aria-controls", whyContentId);

  const whyContent = createElement("div", { classes: ["why-flagged-content"] });
  whyContent.id = whyContentId;
  whyContent.setAttribute("hidden", "");

  // Reasoning chain: statement → factor → assumption → blind spot → question
  const chainSteps = [
    { arrow: "Statement", text: `"${assumption.trigger_statement}"` },
    { arrow: "→ Identified assumption", text: assumption.text },
    { arrow: "→ Why it matters", text: assumption.why_it_matters },
    { arrow: "→ Investigate with", text: assumption.verification_questions[0] ?? "" },
  ];
  for (const step of chainSteps) {
    const stepEl = createElement("div", { classes: ["why-chain-step"] });
    const arrowEl = createElement("span", { classes: ["why-chain-arrow"] });
    arrowEl.textContent = step.arrow;
    const textEl = createElement("span");
    textEl.textContent = step.text;
    stepEl.appendChild(arrowEl);
    stepEl.appendChild(textEl);
    whyContent.appendChild(stepEl);
  }

  whyBtn.addEventListener("click", () => {
    const expanded = whyBtn.getAttribute("aria-expanded") === "true";
    whyBtn.setAttribute("aria-expanded", String(!expanded));
    whyBtn.textContent = expanded ? "▶ Why was this flagged?" : "▼ Why was this flagged?";
    if (expanded) {
      whyContent.setAttribute("hidden", "");
    } else {
      whyContent.removeAttribute("hidden");
    }
  });

  body.appendChild(whyBtn);
  body.appendChild(whyContent);

  // ── Status radio group ──
  const fieldsetId = `status-fieldset-${assumption.id}`;
  const fieldset = createElement("fieldset", { classes: ["status-fieldset"] });
  fieldset.id = fieldsetId;
  const legend = createElement("legend");
  legend.textContent = "Your review status";
  fieldset.appendChild(legend);

  const radioGroup = createElement("div", {
    classes: ["status-radio-group"],
    attrs: { role: "radiogroup", "aria-labelledby": fieldsetId },
  });

  for (const [statusKey, meta] of Object.entries(STATUS_CONFIG)) {
    const radioId = `status-${assumption.id}-${statusKey}`;
    const label = createElement("label", { classes: ["status-radio-label"] });
    label.setAttribute("for", radioId);

    const radio = createElement("input", {
      attrs: {
        type: "radio",
        id: radioId,
        name: `status-${assumption.id}`,
        value: statusKey,
        "aria-label": `${meta.label} — ${meta.icon}`,
      },
    });

    const iconSpan = createElement("span", { classes: ["status-icon"], text: meta.icon });
    iconSpan.setAttribute("aria-hidden", "true");
    const labelText = createElement("span", { text: meta.label });

    label.appendChild(radio);
    label.appendChild(iconSpan);
    label.appendChild(labelText);
    radioGroup.appendChild(label);

    radio.addEventListener("change", () => {
      if (radio.checked) {
        // Update visual state on labels
        radioGroup.querySelectorAll(".status-radio-label").forEach((lbl) => {
          lbl.className = "status-radio-label";
        });
        label.classList.add(`selected-${statusKey}`);

        // Update ledger state
        const existing = ledgerState.get(assumption.id) ?? { status: "unreviewed", note: "" };
        ledgerState.set(assumption.id, { ...existing, status: statusKey });

        // Debounced score update
        updateScore();
        announceToScreenReader(`Assumption "${assumption.id}" marked as: ${meta.label}`);
      }
    });
  }

  fieldset.appendChild(radioGroup);
  body.appendChild(fieldset);

  // ── Note field ──
  const noteField = createElement("textarea", {
    classes: ["assumption-note-field"],
    attrs: {
      id: `note-${assumption.id}`,
      placeholder: "Optional note (your own words)…",
      rows: "2",
      maxlength: "500",
      "aria-label": `Note for assumption: ${assumption.text}`,
    },
  });

  noteField.addEventListener("input", () => {
    const existing = ledgerState.get(assumption.id) ?? { status: "unreviewed", note: "" };
    ledgerState.set(assumption.id, { ...existing, note: noteField.value });
  });

  body.appendChild(noteField);

  card.appendChild(header);
  card.appendChild(body);
  return card;
}

// ─── Score Update ────────────────────────────────────────────────────────────

/** Debounce timer for score updates */
let _scoreDebounce = null;

/**
 * Call the /api/score endpoint and update the score panel.
 * Debounced to avoid rapid successive calls.
 */
function updateScore() {
  clearTimeout(_scoreDebounce);
  _scoreDebounce = setTimeout(async () => {
    const ledger = Array.from(ledgerState.entries()).map(([id, { status, note }]) => ({
      assumption_id: id,
      status,
      note,
    }));

    try {
      const response = await fetch(`${API_BASE}/api/score`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ledger }),
      });
      if (!response.ok) return;
      const data = await response.json();
      setScore(data.score, data.label);
    } catch {
      // Score update failure is non-blocking
    }
  }, 300);
}

/**
 * Update the score panel UI.
 * @param {number} score - 0 to 100
 * @param {string} label
 */
function setScore(score, label) {
  const scoreNum   = el("score-number");
  const scoreBar   = el("score-bar");
  const scoreLabelVal = el("score-label-value");

  setText(scoreNum, String(score));
  scoreBar.style.width = `${score}%`;
  setText(scoreLabelVal, `${score} — ${label}`);

  announceToScreenReader(`Reasoning Completeness Score: ${score} — ${label}`);
}

// ─── Receipt ─────────────────────────────────────────────────────────────────

/**
 * Generate, display, and reveal copy/download buttons for the receipt.
 */
async function generateReceipt() {
  if (!currentAnalysis) return;

  const ledger = Array.from(ledgerState.entries()).map(([id, { status, note }]) => ({
    assumption_id: id,
    status,
    note,
  }));

  const decisionLog = {
    my_decision:              el("my-decision").value.trim() || "(not provided)",
    main_reasons:             el("main-reasons").value.trim(),
    what_could_change_my_mind: el("what-could-change").value.trim(),
    next_action:              el("next-action").value.trim(),
    review_date:              el("review-date").value,
    confidence:               el("confidence").value.trim(),
  };

  if (!decisionLog.my_decision || decisionLog.my_decision === "(not provided)") {
    const confirmed = window.confirm("You have not entered your decision yet. Generate the receipt anyway?");
    if (!confirmed) { el("my-decision").focus(); return; }
  }

  try {
    const response = await fetch(`${API_BASE}/api/receipt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        analysis: currentAnalysis,
        ledger,
        decision_log: decisionLog,
      }),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error ?? "Receipt generation failed.");
    }

    const data = await response.json();
    const receiptPre = el("receipt-text");
    setText(receiptPre, data.text);  // Safe — textContent only

    show(el("receipt-output"));
    show(el("copy-receipt-btn"));
    show(el("download-receipt-btn"));
    el("receipt-output").scrollIntoView({ behavior: "smooth", block: "start" });
    announceToScreenReader("Decision receipt generated successfully.");
  } catch (err) {
    alert("Could not generate receipt: " + err.message);
  }
}

/** Copy receipt text to clipboard. */
async function copyReceipt() {
  const text = el("receipt-text").textContent;
  try {
    await navigator.clipboard.writeText(text);
    const btn = el("copy-receipt-btn");
    const orig = btn.textContent;
    btn.textContent = "Copied!";
    setTimeout(() => { btn.textContent = orig; }, 2000);
    announceToScreenReader("Receipt copied to clipboard.");
  } catch {
    alert("Copy failed. Please select the text and copy manually.");
  }
}

/** Download receipt as a .txt file. */
function downloadReceipt() {
  const text = el("receipt-text").textContent;
  const blob = new Blob([text], { type: "text/plain" });
  const url  = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "blindspot-ai-decision-receipt.txt";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  announceToScreenReader("Receipt downloaded as .txt file.");
}

/** Reset everything for a new analysis. */
function resetForNewAnalysis() {
  currentAnalysis = null;
  ledgerState.clear();
  hide(el("results-section"));
  hide(el("pii-warning"));
  show(el("intake-section"));
  el("intake-form").reset();

  // Reset char counters
  ["decision-field", "options-field", "reasons-field", "priorities-field", "constraints-field", "concerns-field"].forEach(id => {
    const field = document.getElementById(id);
    if (field) field.dispatchEvent(new Event("input"));
  });

  // Hide receipt
  hide(el("receipt-output"));
  hide(el("copy-receipt-btn"));
  hide(el("download-receipt-btn"));

  el("intake-section").scrollIntoView({ behavior: "smooth", block: "start" });
  announceToScreenReader("Form reset. You can start a new analysis.");
}

// ─── Init ─────────────────────────────────────────────────────────────────────

/**
 * Attach all event listeners after the DOM is ready.
 */
function init() {
  // Character counters
  attachCounter("decision-field",    "decision-count",    500);
  attachCounter("options-field",     "options-count",     500);
  attachCounter("reasons-field",     "reasons-count",     1000);
  attachCounter("priorities-field",  "priorities-count",  500);
  attachCounter("constraints-field", "constraints-count", 500);
  attachCounter("concerns-field",    "concerns-count",    500);

  // Demo loader
  el("load-demo-btn").addEventListener("click", loadDemo);

  // Form submit
  el("intake-form").addEventListener("submit", handleFormSubmit);

  // New analysis
  el("new-analysis-btn").addEventListener("click", resetForNewAnalysis);

  // Receipt actions
  el("generate-receipt-btn").addEventListener("click", generateReceipt);
  el("copy-receipt-btn").addEventListener("click", copyReceipt);
  el("download-receipt-btn").addEventListener("click", downloadReceipt);
}

// Start when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
