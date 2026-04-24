"""Policy Agent — compliance check against the rulebook.

Reads the JSON policy store, the extracted claim, and the intelligence
report, and decides which rules apply and which are violated. Produces
a structured `PolicyReport`; blocking violations short-circuit the
workflow to rejection.
"""
from __future__ import annotations

from langsmith import traceable

from ..config import settings
from ..llm import chat_structured
from ..schemas import PolicyReport
from ..state import WorkflowState
from ..tools import PolicyStore

_policies = PolicyStore()

SYSTEM = """You are the Policy Agent. Compare the extracted claim and
the intelligence report against the company reimbursement policy. For
each rule, decide whether it applies; for applied rules, decide whether
the claim violates it.

Rules:
- A violation of a `block`-severity rule sets `compliant=false` and must
  appear in `violations`.
- A violation of a `warn`-severity rule appears in `violations` but does
  not necessarily set `compliant=false` (use judgement — warns accumulate).
- `applied_rules` is the list of rule_ids you actually evaluated.
- `summary` is 1-3 sentences, written for a human reviewer.

When the intelligence report says `is_likely_duplicate=true` AND the
existing licence has available seats, treat POL-006 as violated.
"""


@traceable(run_type="chain", name="agent.policy")
def policy_node(state: WorkflowState) -> WorkflowState:
    claim = state["intake"]
    intel = state.get("intelligence")

    user_msg = f"""{_policies.as_prompt_block()}

Claim under review:
- vendor: {claim.vendor}
- product: {claim.product}
- category: {claim.category}
- amount_myr: {claim.amount_myr}
- billing_period: {claim.billing_period}
- purchase_date: {claim.purchase_date}
- justification: {claim.business_justification}
- missing_fields: {claim.missing_fields}

Intelligence report summary:
- is_likely_duplicate: {intel.is_likely_duplicate if intel else 'n/a'}
- recommendation: {intel.recommendation if intel else 'n/a'}
- rationale: {intel.rationale if intel else 'n/a'}

Produce the policy report now."""

    report = chat_structured(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        PolicyReport,
        cfg=settings.cfg_policy,
    )

    trace = state.get("trace", []) + ["policy"]
    return {**state, "policy": report, "trace": trace}
