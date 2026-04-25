# Orion Tools — v2 Plan

This document describes every tool-level change required for v2.
Current tool state is in `docs/tools.md`.

---

## Summary of Tool Changes

| File | Status | Change |
|---|---|---|
| `document_parser.py` | UNCHANGED | Digital-only scope — no vision fallback (see README limitation) |
| `amount_extractor.py` | **NEW** | Regex currency extractor — deterministic anti-hallucination guard |
| `policy_engine.py` | **NEW** | Deterministic hard-rule evaluator (replaces `policy.py` entirely) |
| `ledger_search.py` | MODIFY | Return pre-computed anomaly signals (z-score, spike flags, duplicate counts) |
| `ledger.py` | UNCHANGED | |
| `policy_store.py` | RETIRE | No longer used in main graph; kept for reference only |
| `subscription_catalog.py` | UNCHANGED | |

---

## `document_parser.py` — UNCHANGED

Orion v2 scopes document parsing to **digitally-generated PDFs and DOCX files only**. No vision/OCR fallback is implemented. `pypdf` and `python-docx` continue to handle all parsing.

**Scanned receipts and image-based PDFs are an explicit limitation** — documented in README. If an uploaded PDF returns empty text, Intake will report `confidence < 0.6` and `missing_fields` will include `receipt_text`. The Supervisor can then route to `request_user_clarification` asking the employee to paste the receipt text manually.

---

## `amount_extractor.py` — NEW

**File:** `app/tools/amount_extractor.py`

### Purpose
Deterministic regex pass over receipt text to extract the largest currency token.
Used by Intake to cross-check the employee's claimed amount against what the receipt actually shows.

### Implementation

```python
"""
Deterministic currency token extractor.
Called by Intake before the LLM processes the receipt, providing a ground-truth
amount anchor that reduces hallucination risk.
"""
import re
from typing import Optional

# Matches: RM 48.50, MYR48.50, $485.00, €1,200.00, 250.00
_CURRENCY_RE = re.compile(
    r'(?:RM|MYR|USD|SGD|\$|€|£|¥)?\s*(\d{1,6}(?:[,\.]\d{2,3})?)',
    re.IGNORECASE,
)

def extract_largest_amount(text: str) -> Optional[float]:
    """
    Return the largest numeric currency token found in text.
    Handles both comma-decimal (EU) and dot-decimal (US/MY) formats.
    Returns None if no currency token found.
    """
    if not text:
        return None

    candidates = []
    for match in _CURRENCY_RE.finditer(text):
        raw = match.group(1).replace(',', '.')
        try:
            val = float(raw)
            # Filter noise: amounts < 0.50 or > 1,000,000 are almost certainly not prices
            if 0.50 <= val <= 1_000_000:
                candidates.append(val)
        except ValueError:
            pass

    return max(candidates) if candidates else None


def amount_discrepancy_flag(
    regex_amount: Optional[float],
    claimed_amount: Optional[float],
    threshold_pct: float = 20.0,
) -> bool:
    """
    Return True if regex_amount and claimed_amount diverge by more than threshold_pct%.
    Used by Intake to set confidence < 0.6 and add a note.
    """
    if regex_amount is None or claimed_amount is None or claimed_amount == 0:
        return False
    pct_diff = abs(regex_amount - claimed_amount) / claimed_amount * 100
    return pct_diff > threshold_pct
```

### Usage in `intake.py`

```python
from app.tools.amount_extractor import extract_largest_amount, amount_discrepancy_flag

# Before calling the LLM:
regex_amount = extract_largest_amount(submission.receipt_text or "")
has_discrepancy = amount_discrepancy_flag(regex_amount, claimed_amount_from_text)

# Inject into prompt:
if regex_amount:
    hint = f"\nRECEIPT CROSS-CHECK: Regex found largest amount = {regex_amount} MYR. "
    if has_discrepancy:
        hint += f"This DIVERGES from claimed amount. Flag in notes, set confidence < 0.6."
```

---

## `policy_engine.py` — NEW

**File:** `app/tools/policy_engine.py`

### Purpose
Deterministic, zero-LLM evaluation of hard expense policy rules.
Replaces the Policy LLM agent for rules that have unambiguous boolean logic.
Returns pre-classified violations + ambiguous flags for Supervisor soft-rule reasoning.

### Implementation

```python
"""
Deterministic policy engine for hard-coded expense rules.
No LLM calls. Fast, auditable, zero hallucination risk.
"""
from __future__ import annotations
from typing import Optional
from app.schemas import IntakeClaim, PolicyViolation, HardPolicyResult

APPROVED_CATEGORIES = {
    "productivity", "design", "engineering", "ai_tools",
    "communication", "analytics", "security",
}

def evaluate_hard_rules(
    claim: IntakeClaim,
    receipt_text: Optional[str],
    is_likely_duplicate: bool = False,
) -> HardPolicyResult:
    """
    Evaluate all hard rules deterministically.
    Returns blocking violations, routing tier hints, and soft flags separately.
    """
    violations: list[PolicyViolation] = []
    routing_hints: list[str] = []    # amount-tier routing signals (NOT violations)
    ambiguous_flags: list[str] = []  # soft rules needing Supervisor judgment

    amount = claim.amount_myr or 0.0
    justification = claim.business_justification or ""

    # AMT-TIER-1/2/3: Amount-tier routing signals (NOT violations)
    if amount <= 500:
        routing_hints.append("auto_approve_eligible")
    elif amount <= 5000:
        routing_hints.append("manager_approval_required")
    else:
        routing_hints.append("finance_approval_required")

    # POL-004: Business justification (HARD BLOCK)
    if len(justification.strip()) < 10:
        violations.append(PolicyViolation(
            rule_id="POL-004",
            description=f"Business justification too short ({len(justification.strip())} chars, minimum 10).",
            severity="block",
        ))

    # POL-005: Approved category (HARD BLOCK)
    if claim.category and claim.category not in APPROVED_CATEGORIES:
        violations.append(PolicyViolation(
            rule_id="POL-005",
            description=f"Category '{claim.category}' is not in the approved list.",
            severity="block",
        ))

    # POL-006: NOT evaluated here — reconciled in merge_intel_policy_node after
    # Intelligence completes (parallel execution race condition — see workflow.md)

    # POL-007: Receipt required > MYR 100 (HARD BLOCK)
    if amount > 100 and not (receipt_text and len(receipt_text.strip()) > 10):
        violations.append(PolicyViolation(
            rule_id="POL-007",
            description=f"Claim of MYR {amount} requires a receipt, but none was provided or parsed.",
            severity="block",
        ))

    # POL-008: Annual plan preference (SOFT — flag for Supervisor)
    if claim.billing_period == "monthly" and amount > 200:
        ambiguous_flags.append(
            f"annual_plan_preferred: monthly billing at MYR {amount} — check if annual option available"
        )

    # Low confidence flag (from Intake regex cross-check or missing fields)
    if claim.confidence < 0.6:
        ambiguous_flags.append(
            f"low_intake_confidence: {claim.confidence:.2f} — possible parsing issue"
        )

    fast_reject = any(v.severity == "block" for v in violations)

    return HardPolicyResult(
        hard_violations=violations,
        routing_hints=routing_hints,
        ambiguous_flags=ambiguous_flags,
        fast_reject=fast_reject,
    )
```

**New schemas needed in `schemas.py`:**
```python
class HardPolicyResult(BaseModel):
    hard_violations: list[PolicyViolation]   # block-severity rules that fired
    routing_hints: list[str]                 # amount-tier routing signals (NOT violations)
    ambiguous_flags: list[str]              # soft rules for Supervisor judgment
    fast_reject: bool
```

**Updated `PolicyReport` schema (replaces existing):**
```python
class PolicyReport(BaseModel):
    compliant: bool
    applied_rules: list[str]
    hard_violations: list[PolicyViolation]   # block-severity only
    routing_hints: list[str]                 # amount-tier signals
    ambiguous_flags: list[str]              # soft flags for Supervisor
    fast_reject: bool
    summary: str
```

---

## `ledger_search.py` — MODIFY

### Current State
Four `@tool`-decorated functions returning raw ledger rows. The LLM must infer patterns from raw data.

### v2 Changes: Pre-Computed Anomaly Signals

All four tools keep the same function signature (backward compatible) but add a `signals` block to their return JSON.

#### `search_employee_history` — Add Spike Detection

```python
import statistics, datetime

def _compute_spike_signals(claims: list[dict], days_back: int) -> dict:
    """Z-score based spike detection. Pure Python math."""
    if not claims:
        return {"spike_detected": False, "z_score": 0.0, "avg_weekly_rate": 0.0,
                "current_week_count": 0, "is_anomaly": False}

    # Group by ISO week
    week_counts: dict[str, int] = {}
    for c in claims:
        dt = datetime.datetime.fromisoformat(c["recorded_at"])
        week_key = dt.strftime("%Y-W%W")
        week_counts[week_key] = week_counts.get(week_key, 0) + 1

    counts = list(week_counts.values())
    if len(counts) < 2:
        return {"spike_detected": False, "z_score": 0.0,
                "avg_weekly_rate": counts[0] if counts else 0,
                "current_week_count": counts[0] if counts else 0, "is_anomaly": False}

    mean = statistics.mean(counts)
    stdev = statistics.stdev(counts) or 0.001   # prevent div-zero
    current_week = max(week_counts, key=week_counts.get)
    current_count = week_counts[current_week]
    z_score = (current_count - mean) / stdev

    return {
        "spike_detected": z_score > 2.0,
        "z_score": round(z_score, 2),
        "avg_weekly_rate": round(mean, 2),
        "current_week_count": current_count,
        "is_anomaly": z_score > 2.0,
        "weeks_analyzed": len(counts),
    }
```

**Updated return shape:**
```json
{
  "employee_id": "E007",
  "days_back": 90,
  "recent_claims": [...],
  "total_in_window": 8,
  "all_time_total": 12,
  "anomaly_signals": {
    "spike_detected": true,
    "z_score": 3.2,
    "avg_weekly_rate": 0.5,
    "current_week_count": 4,
    "is_anomaly": true,
    "weeks_analyzed": 13
  }
}
```

#### `search_ledger_by_amount` — Add Duplicate Signals

> **Bug fix (Q6):** The original draft had `amount` undefined inside `_compute_duplicate_signals`. The function now takes `amount` and `tolerance_pct` as explicit parameters, and uses float-range comparison instead of `==` to handle currency parsing inconsistencies.

```python
def _compute_duplicate_signals(
    matches: list[dict],
    employee_id: str,
    amount: float,
    tolerance_pct: float = 1.0,   # "exact" = within 1%
) -> dict:
    if not matches:
        return {"exact_duplicate_count": 0, "near_duplicate_count": 0,
                "same_employee_matches": 0, "last_seen_days_ago": None}

    same_emp = [m for m in matches if m.get("employee_id") == employee_id]
    now = datetime.datetime.utcnow()
    days_ago = None
    if matches:
        latest = max(matches, key=lambda m: m["recorded_at"])
        dt = datetime.datetime.fromisoformat(latest["recorded_at"].replace("Z", "+00:00"))
        days_ago = (now - dt.replace(tzinfo=None)).days

    # Float-range comparison: "exact" = within tolerance_pct% of queried amount
    def _within_tolerance(m: dict) -> bool:
        match_amt = m.get("amount_myr", 0)
        if amount == 0:
            return match_amt == 0
        return abs(match_amt - amount) / amount * 100 <= tolerance_pct

    return {
        "exact_duplicate_count": len([m for m in matches if _within_tolerance(m)]),
        "near_duplicate_count": len(matches),
        "same_employee_matches": len(same_emp),
        "last_seen_days_ago": days_ago,
    }
```

Call site update — pass `amount` and `tolerance_pct` explicitly:
```python
signals = _compute_duplicate_signals(matches, employee_id=employee_id, amount=amount, tolerance_pct=1.0)
```

**Updated return shape:**
```json
{
  "matches": [...],
  "count": 2,
  "duplicate_signals": {
    "exact_duplicate_count": 1,
    "near_duplicate_count": 2,
    "same_employee_matches": 1,
    "last_seen_days_ago": 28
  }
}
```

#### `search_ledger_by_merchant` — Add Vendor Frequency Signals

```python
def _compute_vendor_signals(matches: list[dict], employee_id: str) -> dict:
    """All three fields are required. employee_claim_count is the primary demo signal."""
    if not matches:
        return {"recurring_pattern_detected": False, "claim_frequency_days": None,
                "employee_claim_count": 0, "unique_employee_count": 0, "total_claims": 0}

    # employee_claim_count: how many times THIS employee has claimed from this vendor
    # Primary duplicate signal — "Sarah has claimed at NotionLabs 3 times in 90 days"
    employee_claim_count = len([m for m in matches if m.get("employee_id") == employee_id])

    # unique_employee_count: vendor risk signal — vendor only 1 employee uses is suspicious
    unique_employees = len({m.get("employee_id") for m in matches if m.get("employee_id")})

    # Recurring pattern: inter-claim interval < 35 days (monthly-ish)
    sorted_claims = sorted(matches, key=lambda m: m["recorded_at"])
    if len(sorted_claims) >= 2:
        dates = [datetime.datetime.fromisoformat(m["recorded_at"].replace("Z", "+00:00"))
                 for m in sorted_claims]
        intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        avg_interval = statistics.mean(intervals) if intervals else None
        recurring = avg_interval is not None and avg_interval < 35
    else:
        avg_interval = None
        recurring = False

    return {
        "recurring_pattern_detected": recurring,
        "claim_frequency_days": round(avg_interval, 1) if avg_interval else None,
        "employee_claim_count": employee_claim_count,
        "unique_employee_count": unique_employees,
        "total_claims": len(matches),
    }
```

> **Call site:** `employee_id` must be passed from the tool function. `search_ledger_by_merchant` already has access to the claim context via the Intelligence agent's tool-calling loop — the LLM must pass the current `employee_id` as part of its tool invocation context, or it can be injected from state before the loop starts.

---

## `policy_store.py` — RETIRE

No longer invoked in the main graph. The policy engine reads `data/policies.json` directly.

Keep the file in place for backward compatibility (smoke tests may reference it). Add a deprecation comment at the top:

```python
# DEPRECATED in v2 — superseded by app/tools/policy_engine.py
# Retained for backward compatibility only. Do not use in new agent code.
```

---

## Data File Seed Requirements

### `data/ledger.json` — 80+ Records Required

The Intelligence agent's tools only detect anomalies if baseline data exists. Current ledger has 3 records — effectively empty for detection purposes.

**Required fraud traps (minimum set for demo):**

| Trap | Employee | Vendor | Amount | Date Pattern | Count |
|---|---|---|---|---|---|
| Duplicate claim | E003 | Notion Labs Inc. | MYR 250 | 2026-03-05 + 2026-04-03 | 2 |
| Uber spike | E007 | Grab / Uber | MYR 18–25 | 5 months × 1, then week of 2026-04-20 × 4 | 9 |
| Monthly SaaS recurring | E003 | Notion Labs Inc. | MYR 250 | 6 consecutive months | 6 |
| Amount mismatch bait | E011 | Starbucks | MYR 485 (actual: MYR 48.50) | 2026-04-22 | 1 |
| Clean baseline | E001–E015 | Various | MYR 50–400 | Scattered 6 months | ~65 |

Total: ~83 records.

See `plan/seed_data.md` for the complete JSON.

### `data/org_subscriptions.json` — Expand to 30+ Licenses

The `lookup_subscription_catalog` tool needs enough entries to produce meaningful hits. Current catalog has 5 active licenses and 6 approved catalog entries — not enough for the demo.

Target:
- **30 active_licenses** covering productivity, design, engineering, AI, communication, analytics, security categories
- **35 approved_catalog entries** covering the same categories plus common alternatives

See `plan/seed_data.md` for the complete expanded catalog JSON.
