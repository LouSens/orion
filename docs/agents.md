# Orion Agents — Current Implementation Reference

This document describes each agent exactly as implemented in the codebase.

---

## 1. Intake Agent — `app/agents/intake.py`

**Role:** Data normaliser — unstructured → structured.

**Input:** `ReimbursementSubmission` (employee free-text + receipt/invoice text)

**Mechanism:** Regex currency pre-pass, then a single `chat_structured()` call.

**Regex pre-pass (anti-hallucination guard):**
Before the LLM runs, `extract_largest_amount()` from `app/tools/amount_extractor.py`
scans the receipt text for currency tokens (handles RM, MYR, USD, €, £, ¥) and finds
the largest value. If the LLM's extracted amount diverges from the regex value by
more than 20%, `confidence` is forced below `0.6` to flag the discrepancy downstream.

**Output schema:** `IntakeClaim` (app/schemas.py)

**Key fields:**
- `vendor`, `product`, `category`, `amount_myr`, `currency_original`, `amount_original`
- `billing_period`, `purchase_date`, `business_justification`
- `confidence`, `missing_fields`
- `regex_extracted_amount` — the value found by the pre-pass (diagnostic)

---

## 2. Intelligence Agent — `app/agents/intelligence.py`

**Role:** Fraud investigator and duplicate detector.

**Input:** `IntakeClaim` + `ReimbursementSubmission` + org subscription catalog

**Mechanism:** Real **LangChain tool-calling loop** (max `settings.intelligence_max_iterations` = 5 iterations).

The LLM autonomously decides which tools to call, in what order, and whether to
re-call a tool. All four tools return **pre-computed signals** — the LLM narrates
and interprets them; it never calculates scores or ratios itself.

**Tools available (defined in `app/tools/ledger_search.py`):**

| Tool | Args | Returns |
|---|---|---|
| `search_ledger_by_amount` | `amount: float`, `tolerance_pct: float = 10`, `employee_id: str` | Matches + `duplicate_signals` (exact/near counts, same-employee count, last-seen days) |
| `search_ledger_by_merchant` | `merchant_name: str`, `employee_id: str` | Matches + `vendor_signals` (recurring pattern flag, claim frequency, employee count) |
| `search_employee_history` | `employee_id: str`, `days_back: int = 90` | Recent claims + `anomaly_signals` (spike flag, z-score, avg weekly rate, weeks analyzed) |
| `lookup_subscription_catalog` | `merchant_name: str` | Matched active licenses + catalog entries, `found_active`, `found_in_catalog` |

After the loop, a separate `chat_structured()` call synthesises all gathered
evidence into the final `IntelligenceReport`.

If the loop cap is reached without a `done` signal, the report is flagged as **degraded**.

**Output schema:** `IntelligenceReport`

**Key fields:**
- `is_likely_duplicate: bool`
- `duplicate_matches: list[SemanticMatch]`
- `alternatives: list[AlternativeSuggestion]`
- `recommendation: Literal["proceed", "suggest_alternative", "block_duplicate"]`
- `rationale: str`
- `cross_reference_notes: str`

---

## 3. Policy Check — `app/tools/policy_engine.py` (called from `app/graph.py`)

**Role:** Deterministic compliance evaluator — no LLM.

**Input:** `IntakeClaim` + receipt text + `is_likely_duplicate` (from Intelligence)

**Mechanism:** Pure Python rules — zero hallucination risk, fully auditable.

| Rule | Condition | Severity |
|---|---|---|
| POL-004 | Business justification < 10 chars | HARD BLOCK |
| POL-005 | Category not in approved list | HARD BLOCK |
| POL-007 | Amount > MYR 100 with no receipt text | HARD BLOCK |
| POL-006 | `is_likely_duplicate=True` | HARD BLOCK |
| POL-008 | Monthly billing > MYR 200 (prefer annual) | Soft flag |
| Confidence | `intake.confidence < 0.6` | Soft flag |

**Amount-tier routing hints** (advisory only, not hard blocks):
- ≤ MYR 500 → `auto_approve_eligible`
- MYR 500–5000 → `manager_approval_required`
- > MYR 5000 → `finance_approval_required`

**`fast_reject` flag:** Set `True` if any HARD BLOCK violation exists. The graph
routes directly from `merge_intel_policy` to `critic` (skipping Supervisor) when
this flag is set, saving approximately 7 seconds per hard-violation case.

**Output schema:** `PolicyReport` (wraps `HardPolicyResult`)

**Key fields:**
- `compliant: bool`
- `hard_violations: list[PolicyViolation]`
- `routing_hints: list[str]`
- `ambiguous_flags: list[str]`
- `fast_reject: bool`
- `summary: str`

---

## 4. Supervisor Agent — `app/agents/supervisor.py`

**Role:** Dynamic task orchestrator — the central routing brain.

**Input:** Full `WorkflowState` (intake + intelligence + policy)

**Mechanism:** Single `chat_structured()` call at `temperature=0.0` for
deterministic routing. The LLM reasons over all accumulated signals and
chooses one of **five routes**:

| Route value | Next node | Meaning |
|---|---|---|
| `route_to_approval` | `critic` | Clear-cut case — send directly to Critic |
| `route_back_to_intelligence` | `intelligence` | Investigation is shallow; re-investigate |
| `route_back_to_policy` | `policy_check` | New context changes applicable rules |
| `request_human_escalation` | `escalate_node` | Genuinely ambiguous — decline to auto-decide |
| `request_user_clarification` | `clarify_node` | Missing information — return questions, terminate graph |

The Supervisor also emits:
- `reasoning` — 2–4 sentence justification for the routing choice
- `focus_areas` — list of strings passed forward as context
- `clarification_questions` — populated only on `request_user_clarification`

**Loop protection:** `supervisor_visits` is incremented each time the Supervisor
node runs. At `supervisor_visits >= 3`, the LLM call is bypassed and the graph
forces `request_human_escalation`, guaranteeing termination.

**Output schema:** `SupervisorDecision`

---

## 5. Critic Agent — `app/agents/critic.py`

**Role:** Adversarial financial reviewer — the final decision maker.

**Input:** Full `WorkflowState` (intake + intelligence + policy + supervisor)

**Mechanism:** Single `chat_structured()` call. Framed as an adversarial reviewer:
"Find the strongest reason to reject. Only approve when you cannot construct
a defensible counter-argument." This framing reduces false approvals compared to
a neutral reviewer.

**Decision values (`ApprovalDecision` enum):**
- `auto_approve`
- `auto_reject`
- `escalate_manager`
- `escalate_finance`
- `request_info`

Amount thresholds (`auto_approve_limit_myr = MYR 500`, `escalation_limit_myr = MYR 5000`)
are injected as guidance in the prompt, not hard-coded branches, so the LLM can
reason about edge cases.

**Output schema:** `ApprovalOutcome`

**Key fields:**
- `decision: ApprovalDecision`
- `approver_role: str`
- `reason: str`
- `confidence: float`
- `next_action: str`

---

## 6. Recorder Agent — `app/agents/recorder.py`

**Role:** Archivist — deterministic, no LLM.

**Input:** `ApprovalOutcome` + `IntakeClaim` + `ReimbursementSubmission`

**Mechanism:** Constructs a `LedgerRecord` and calls `Ledger.append()` to
persist it to `data/ledger.json`. Sets `notification_sent_to` based on decision:
- `auto_approve` → `["employee:{id}", "role:finance_ops"]`
- `escalate_manager` → `["employee:{id}", "role:direct_manager"]`
- `escalate_finance` → `["employee:{id}", "role:finance_controller"]`
- `auto_reject` → `["employee:{id}"]`

**Output schema:** `LedgerRecord` written to disk; `terminal=True` set on state.

---

## Helper Nodes (in `app/graph.py`, no separate file)

### `merge_intel_policy`

Fan-in passthrough node that runs after the parallel `intelligence` and
`policy_check` branches complete. Reconciles POL-006: if Intelligence found
a likely duplicate, ensures the Policy result reflects it. Then routes via
`_fast_reject_route`.

### `clarify_node`

Terminal node (no LLM). Packages `SupervisorDecision.clarification_questions`
as a `request_info` `ApprovalOutcome`. Reached when Supervisor chooses
`request_user_clarification`. The graph terminates; the frontend displays the
questions for the employee to resubmit with additional detail.

### `escalate_node`

Terminal node (no LLM). Packages Supervisor's `reasoning` as an
`escalate_manager` `ApprovalOutcome`. Reached when Supervisor chooses
`request_human_escalation`.
