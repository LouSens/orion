# Orion Agent Redesign — v2 Plan

This document specifies every agent-level change required for the v2 architecture.
Read alongside `architecture.md`, `tools.md`, and `workflow.md` in this directory.

---

## Summary of Agent Changes

| Agent | Status | Change |
|---|---|---|
| Intake | **MODIFY** | Regex currency cross-check (digital PDFs only — see README for scope limitation) |
| Intelligence | **MODIFY** | Tools return pre-computed anomaly signals; LLM only narrates |
| Policy (`policy.py`) | **DELETE** | Replaced entirely by `policy_engine.py` (deterministic) + Supervisor absorbs soft rules |
| `policy_engine.py` | **NEW** | Deterministic hard-rule evaluator — no LLM |
| Supervisor | **MODIFY** | Replace `route_to_validation` with `request_user_clarification`; add `supervisor_visits` hard counter |
| Validation | **DELETE** | Absorbed into Supervisor's `request_user_clarification` route |
| Approval | **RENAME → Critic** | Adversarial reviewer — tries to *reject*; approves only if no counter-argument found |
| Recorder | **UNCHANGED** | No changes needed |

---

## 1. Intake Agent — `app/agents/intake.py`

### Current State
Single `chat_structured()` call. Reads `receipt_text` (already-parsed text string).
Parser (`document_parser.py`) uses `pypdf` / `python-docx` — both fail silently on image-based PDFs and scanned documents.

### Scope Decision: Digital PDFs Only

**No vision/OCR fallback will be implemented.** Orion v2 scopes to digitally-generated PDFs and DOCX files only. Scanned receipts and image-based PDFs are an explicit limitation documented in the README.

Rationale: Building a reliable OCR pipeline (Tesseract or vision-API) is a scope risk at hackathon speed. Scoped correctly, this is honest and prevents a live demo failure on an unreadable scan.

### v2 Changes

#### A — Regex Currency Cross-Check (Anti-Hallucination Guard)

Before the LLM Intake call, run a deterministic regex pass over `receipt_text`:

```python
import re
_CURRENCY_RE = re.compile(r'[$€£RM]?\s*\d{1,6}(?:[.,]\d{2})?')

def extract_largest_currency(text: str) -> float | None:
    """Return the largest numeric currency token found in text."""
    matches = _CURRENCY_RE.findall(text)
    nums = [float(m.replace(',', '.').strip('$€£RM ')) for m in matches]
    return max(nums) if nums else None
```

Pass **both** values to the Intake LLM prompt:
- `regex_extracted_amount`: The largest number found by the regex (or `None`)
- `employee_claimed_amount`: From the free-text submission

Inject as a prompt hint:
> "The receipt text contains a largest numeric token of **{regex_amount} MYR**. The employee claims **{claimed_amount} MYR**. If these diverge by more than 20%, flag the discrepancy in `notes` and set `confidence` below 0.6."

**Implementation location:** New helper `app/tools/amount_extractor.py`.

#### B — Structured Output for Policy Engine

Add to `IntakeClaim` so `policy_engine.py` can evaluate hard rules without touching the LLM:

```python
regex_extracted_amount: Optional[float] = None   # largest currency token found by regex
```

`vision_extracted` field is **NOT added** — digital-only scope, no vision path.

---

## 2. Intelligence Agent — `app/agents/intelligence.py`

### Current State
Tool-calling loop (max 5 iters). Tools return raw ledger rows. LLM does the math.

### v2 Changes

**Math stays in Python — LLM only narrates.**

#### A — Upgrade Tool Return Values

Each tool must return pre-computed signals alongside raw data. The LLM should never be asked to calculate; only to interpret.

**`search_employee_history` → must return:**
```json
{
  "employee_id": "E003",
  "recent_claims": [...],
  "total_in_window": 6,
  "all_time_total": 12,
  "weekly_claim_counts": {"2026-W15": 4, "2026-W14": 1, "2026-W13": 1},
  "anomaly_signals": {
    "spike_detected": true,
    "z_score": 3.2,
    "avg_weekly_rate": 0.5,
    "current_week_count": 4,
    "is_anomaly": true
  }
}
```

**`search_ledger_by_amount` → must return:**
```json
{
  "matches": [...],
  "count": 2,
  "duplicate_signals": {
    "exact_duplicate_count": 1,
    "near_duplicate_count": 1,
    "same_employee_matches": 1,
    "last_seen_days_ago": 28
  }
}
```

**`search_ledger_by_merchant` → must return:**
```json
{
  "matches": [...],
  "count": 5,
  "vendor_signals": {
    "recurring_pattern_detected": true,
    "claim_frequency_days": 30,
    "employee_claim_count": 3,
    "unique_employee_count": 2,
    "total_claims": 5
  }
}
```

- `employee_claim_count` — how many times *this specific employee* has claimed from this vendor (direct duplicate signal; this is what fires in the demo)
- `unique_employee_count` — how many distinct employees have claimed here (vendor risk signal — a vendor only one employee has ever used is suspicious)
- `total_claims` — company-wide volume at this vendor

#### B — Final Synthesis Prompt Update

After the tool-calling loop, the synthesis `chat_structured()` call should instruct:
> "The tools have already calculated statistical signals. Your job is to **narrate** these signals in plain language, not recalculate them. Use the `anomaly_signals`, `duplicate_signals`, and `vendor_signals` fields directly in your reasoning."

#### C — `supervisor_visits` Counter Integration

Intelligence does not change its own loop, but it must respect the new `supervisor_visits` in state (see Supervisor below). No code change needed in the agent itself.

---

## 3. Policy — `policy.py` DELETED, replaced by `policy_engine.py`

### Current State
Single LLM `chat_structured()` call evaluating all rules (hard + soft mixed).

### v2 Changes

**`app/agents/policy.py` is deleted.** All policy evaluation is handled by:
1. **`app/tools/policy_engine.py`** — deterministic Python for hard rules → runs as `policy_check` graph node
2. **Supervisor** — absorbs all soft-rule judgment via `policy.ambiguous_flags` + `policy.routing_hints` in its prompt

This removes one LLM call, eliminates a node, and keeps the parallel topology clean.

#### `policy_engine.py` — Deterministic Evaluator (No LLM)

**File:** `app/tools/policy_engine.py` (new)
**Graph Node:** `policy_check_node` in `graph.py`

Returns:
```python
class HardPolicyResult(BaseModel):
    hard_violations: list[PolicyViolation]  # BLOCK-severity rules that fired
    routing_hints: list[str]               # amount-tier routing signals (not violations)
    ambiguous_flags: list[str]             # soft rules needing Supervisor judgment
    fast_reject: bool                      # True if any block violation found → short-circuit
```

**Two categories of rules — NOT conflated:**

**Blocking rules → `PolicyViolation` (severity=block):**

| Rule ID | Condition | Python check |
|---|---|---|
| POL-004 | Missing/short business justification | `len(justification.strip()) < 10` |
| POL-005 | Unapproved category | `category not in APPROVED_CATEGORIES` |
| POL-007 | No receipt for claim > MYR 100 | `amount_myr > 100 and not receipt_text` |

**Routing rules → `routing_hints` (NOT violations):** POL-001/002/003 are amount-tier *routing signals*, not violations. Calling them violations is wrong. They determine which approval track is required.

| Signal ID | Condition | Hint string |
|---|---|---|
| AMT-TIER-1 | `amount_myr <= 500` | `"auto_approve_eligible"` |
| AMT-TIER-2 | `500 < amount_myr <= 5000` | `"manager_approval_required"` |
| AMT-TIER-3 | `amount_myr > 5000` | `"finance_approval_required"` |

**Soft rules → `ambiguous_flags` (forwarded to Supervisor for judgment):**
- POL-006 — duplicate subscription: set by merge node after Intelligence runs (see Q8 / merge node reconciliation below)
- POL-008 — annual plan preference: flagged if `billing_period == "monthly" and amount_myr > 200`
- Low confidence: `intake.confidence < 0.6`

**Fast-reject short-circuit:** If `fast_reject=True`, a conditional edge after `merge_intel_policy` routes directly to `critic` as `auto_reject` — bypassing Supervisor and saving 2 LLM calls. See workflow.md.

#### Updated `PolicyReport` Schema

```python
class PolicyReport(BaseModel):
    compliant: bool
    applied_rules: list[str]
    hard_violations: list[PolicyViolation]  # block-severity only
    routing_hints: list[str]               # amount-tier signals for Supervisor
    ambiguous_flags: list[str]             # soft flags for Supervisor
    fast_reject: bool
    summary: str
```

---

## 4. Supervisor Agent — `app/agents/supervisor.py`

### Current State
5-route LLM router. Increments `retry_count`. Passes `focus_areas` to Validation.

### v2 Changes

#### A — Replace `route_to_validation` with `request_user_clarification`

Net routes stays at **5**. `route_to_validation` is dropped (Validation deleted); `request_user_clarification` takes its place. No new route is added — the slot is reused.

```python
class SupervisorRoute(str, Enum):
    route_to_approval           = "route_to_approval"
    route_back_to_intelligence  = "route_back_to_intelligence"
    route_back_to_policy        = "route_back_to_policy"
    request_human_escalation    = "request_human_escalation"
    request_user_clarification  = "request_user_clarification"  # replaces route_to_validation
    # route_to_validation — REMOVED
```

**`SupervisorDecision` schema update:**
```python
class SupervisorDecision(BaseModel):
    route: SupervisorRoute
    reasoning: str
    focus_areas: list[str] = []
    clarification_questions: list[str] = Field(
        default_factory=list,
        description="Populated only when route=request_user_clarification. 1-3 specific questions."
    )
```

When `route = request_user_clarification`, the graph terminates immediately, returning the questions to the frontend. No Validation agent invoked.

#### B — Hard Loop Guard: `supervisor_visits`

**Add to `WorkflowState`:**
```python
supervisor_visits: int  # NEW — separate from retry_count
```

**In `supervisor_node`:**
```python
visits = state.get("supervisor_visits", 0) + 1
if visits >= 3:
    # Bypass LLM routing — force escalation
    return {**state, "supervisor_visits": visits, "supervisor": SupervisorDecision(
        route=SupervisorRoute.request_human_escalation,
        reasoning=f"Auto-escalated: supervisor_visits={visits} exceeded limit of 3.",
    )}
# ... normal LLM call
```

This is a **separate counter from `retry_count`** — `retry_count` tracks loop-backs; `supervisor_visits` tracks every entry into the supervisor node (including the first).

#### C — Absorb Soft Policy Reasoning

The Supervisor prompt is updated to include:
1. `policy.ambiguous_flags` — soft rule flags from Layer 1 policy engine
2. `intake.confidence` — low confidence triggers clarification route
3. `intake.regex_extracted_amount` vs `intake.amount_myr` — cross-check discrepancy

---

## 5. Validation Agent — `app/agents/validation.py`

### Status: **DELETED**

Validation is removed from the graph. Its role is absorbed by:
- **Supervisor's `request_user_clarification` route** — terminates graph with structured questions
- **Intake's `confidence` + `missing_fields`** — upstream gap detection
- **Policy engine's `ambiguous_flags`** — business-purpose vagueness flagged deterministically

**Files to remove:** `app/agents/validation.py`
**Schema to remove:** `ValidationReport`, `ClarificationRequest` from `schemas.py`
**State field to remove:** `validation: ValidationReport` from `WorkflowState`
**Graph nodes to remove:** `validation`, `request_info`, `_post_validation_route`

---

## 6. Approval Agent → Critic Agent — `app/agents/critic.py`

### Current State
Named "Approval". Single `chat_structured()` call. Emits approve/reject/escalate.

### v2 Changes: Adversarial Reviewer (Actor-Critic Pattern)

**Rename file:** `app/agents/approval.py` → `app/agents/critic.py`
**Rename node:** `approval_node` → `critic_node`

#### New Prompt Design (Adversarial Framing)

> "You are the Critic agent. Your job is to **find the strongest possible reason to REJECT this claim**. Search for inconsistencies, policy violations, missing evidence, or risk signals in the accumulated reports. If you cannot find a defensible counter-argument, then approve. If you can, reject or escalate.
>
> This adversarial stance is not a bias — it is a financial control mechanism. Every false approval costs the company money."

**`ApprovalOutcome` schema unchanged** — same enum values. Only the framing changes.

The pitch for judges: *"We use adversarial agent review for financial decisions — our Critic agent tries to reject every claim and only approves when it cannot find a counter-argument."*

---

## 7. Recorder Agent — `app/agents/recorder.py`

### Status: **UNCHANGED**

No modifications required.

---

## New Helper: `app/tools/amount_extractor.py`

```python
"""Deterministic currency token extractor for receipt cross-checking."""
import re
from typing import Optional

_CURRENCY_RE = re.compile(r'(?:RM|MYR|USD|\$|€|£)?\s*(\d{1,6}(?:[.,]\d{2})?)')

def extract_largest_amount(text: str) -> Optional[float]:
    """Return the largest numeric currency token in text, or None."""
    if not text:
        return None
    raw = _CURRENCY_RE.findall(text)
    nums = []
    for m in raw:
        try:
            nums.append(float(m.replace(',', '.')))
        except ValueError:
            pass
    return max(nums) if nums else None
```

---

## New Helper: `app/tools/policy_engine.py`

Deterministic hard-rule evaluator. No LLM. See Layer 1 description above for full spec.

---

## LLM Call Count Comparison

| Stage | v1 calls | v2 calls | Notes |
|---|---|---|---|
| Intake | 1 | 1 | Digital-only scope; no vision overhead |
| Intelligence loop | up to 5 | up to 5 | Tools return pre-computed signals; LLM narrates |
| Intelligence synthesis | 1 | 1 | |
| Policy (all rules) | 1 (LLM) | 0 | **Python deterministic — `policy_engine.py`** |
| Supervisor | 1 | 1 | 5 routes (replaced `route_to_validation`) |
| Validation | 1 | 0 | **DELETED** |
| Approval/Critic | 1 | 1 | Adversarial framing only |
| **Total (typical)** | **~11** | **~9** | -2 mandatory LLM calls |
| **Fast-reject path** | ~11 | **~3** | Policy block → short-circuit before Supervisor |
| **Parallel benefit** | Sequential | **Intel ∥ policy_check** | Policy 0s on critical path |
