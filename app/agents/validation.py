"""Validation Agent — ambiguity + missing data handler.

Decides whether there's enough signal to make a decision. If not, it
generates targeted clarification questions so the UI can round-trip
them to the employee. This is how we meet the "ambiguity / incomplete
data" bar without hard-coding rules for every missing field.
"""
from __future__ import annotations

from langsmith import traceable

from ..config import settings
from ..llm import chat_structured
from ..schemas import ValidationReport
from ..state import WorkflowState

SYSTEM = """You are the Validation Agent. Given the extracted claim, the
intelligence report, and the policy report, decide if we have enough
information to make a reimbursement decision.

Principles:
- Do NOT demand clarifications for information that is irrelevant to the
  decision. For example, if the claim is already a clear policy block
  (duplicate with seats available), there's no value in asking for a
  missing purchase date — route to decision directly.
- When `ready_for_decision=false`, produce 1-3 highly targeted questions
  in `clarifications`. Each question must name the exact field it fills.
- When extraction confidence is low (<0.5) AND the claim is plausibly
  approvable, ask clarifying questions rather than rejecting.
- `summary` explains to a human why you chose this path.
"""


@traceable(run_type="chain", name="agent.validation")
def validation_node(state: WorkflowState) -> WorkflowState:
    claim = state["intake"]
    intel = state.get("intelligence")
    policy = state.get("policy")

    user_msg = f"""Extracted claim:
- vendor: {claim.vendor}
- product: {claim.product}
- amount_myr: {claim.amount_myr}
- billing_period: {claim.billing_period}
- justification: {claim.business_justification}
- missing_fields: {claim.missing_fields}
- extraction_confidence: {claim.confidence}

Intelligence:
- recommendation: {intel.recommendation if intel else 'n/a'}
- is_likely_duplicate: {intel.is_likely_duplicate if intel else 'n/a'}

Policy:
- compliant: {policy.compliant if policy else 'n/a'}
- violations: {[v.rule_id for v in (policy.violations if policy else [])]}

Decide ready_for_decision and clarifications."""

    report = chat_structured(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        ValidationReport,
        cfg=settings.cfg_validation,
    )

    trace = state.get("trace", []) + ["validation"]
    return {**state, "validation": report, "trace": trace}
