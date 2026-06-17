"""Deterministic policy engine for hard-coded expense rules.

No LLM calls. Fast, auditable, zero hallucination risk.
Rule metadata (which rules exist, their severity tier) comes from
policies.json via PolicyStore. Conditional logic lives here in Python.
"""
from __future__ import annotations

from typing import Optional

from ..schemas import HardPolicyResult, PolicyViolation
from .policy_store import PolicyStore

_store = PolicyStore()

APPROVED_CATEGORIES = {
    "productivity", "design", "engineering", "ai_tools",
    "communication", "analytics", "security",
}


def evaluate_hard_rules(
    claim,  # IntakeClaim — avoid circular import at module level
    receipt_text: Optional[str],
    is_likely_duplicate: bool = False,
) -> HardPolicyResult:
    """Evaluate all hard rules deterministically.

    Returns blocking violations, routing tier hints, and soft flags separately.
    POL-006 (duplicate subscription) is NOT evaluated here — it is reconciled
    in merge_intel_policy_node after the parallel Intelligence branch completes.
    """
    violations: list[PolicyViolation] = []
    routing_hints: list[str] = []
    ambiguous_flags: list[str] = []

    amount = claim.amount_myr or 0.0
    justification = claim.business_justification or ""

    # AMT-TIER routing signals (not violations — no matching policy row)
    if amount <= 500:
        routing_hints.append("auto_approve_eligible")
    elif amount <= 5000:
        routing_hints.append("manager_approval_required")
    else:
        routing_hints.append("finance_approval_required")

    # POL-004: Business justification too short
    if len(justification.strip()) < 10:
        violations.append(PolicyViolation(
            rule_id="POL-004",
            description=f"Business justification too short ({len(justification.strip())} chars, minimum 10).",
            severity=_store.severity_for("POL-004"),
        ))

    # POL-005: Unapproved category
    # "other" is a soft flag — transport/misc expenses are valid but need review.
    if claim.category and claim.category not in APPROVED_CATEGORIES:
        if claim.category == "other":
            ambiguous_flags.append(
                "uncategorized_expense: category is 'other' — supervisor should confirm business purpose"
            )
        else:
            violations.append(PolicyViolation(
                rule_id="POL-005",
                description=f"Category '{claim.category}' is not in the approved list.",
                severity=_store.severity_for("POL-005"),
            ))

    # POL-007: Receipt required for claims > MYR 100
    if amount > 100 and not (receipt_text and len(receipt_text.strip()) > 10):
        violations.append(PolicyViolation(
            rule_id="POL-007",
            description=f"Claim of MYR {amount} requires a receipt, but none was provided or parsed.",
            severity=_store.severity_for("POL-007"),
        ))

    # POL-008: Annual plan preference (soft — forward to Supervisor)
    if claim.billing_period == "monthly" and amount > 200:
        ambiguous_flags.append(
            f"annual_plan_preferred: monthly billing at MYR {amount} — check if annual option available"
        )

    # Low confidence flag
    if claim.confidence < 0.6:
        ambiguous_flags.append(
            f"low_intake_confidence: {claim.confidence:.2f} — possible parsing issue or amount mismatch"
        )

    fast_reject = any(v.severity == "block" for v in violations)

    return HardPolicyResult(
        hard_violations=violations,
        routing_hints=routing_hints,
        ambiguous_flags=ambiguous_flags,
        fast_reject=fast_reject,
    )
