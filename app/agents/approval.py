"""Approval Agent — final decision with routing.

Synthesises the full state and emits the terminal decision:
auto_approve / auto_reject / escalate_manager / escalate_finance /
request_info. The LLM reasons — thresholds are given as context, not
hard-coded branches — so it can justifiably deviate (e.g. auto-approve
a MYR 520 Notion seat-request over the nominal MYR 500 threshold when
the intelligence report is unambiguous).
"""
from __future__ import annotations

from langsmith import traceable

from ..config import settings
from ..llm import chat_structured
from ..schemas import ApprovalDecision, ApprovalOutcome
from ..state import WorkflowState

SYSTEM = f"""You are the Approval Agent. Synthesise the full case file
and emit one decision: {', '.join(d.value for d in ApprovalDecision)}.

Guidance (NOT rigid):
- auto_approve: compliant, no violations, amount <= MYR {settings.auto_approve_limit_myr:.0f},
  intelligence says 'proceed', validation ready.
- auto_reject: blocking policy violation (including duplicate with seats
  available) OR intelligence says 'block_duplicate'. Name the reason.
- escalate_manager: compliant but amount MYR {settings.auto_approve_limit_myr:.0f}-{settings.escalation_limit_myr:.0f},
  OR warn-level violations present, OR intelligence suggests alternative.
- escalate_finance: amount > MYR {settings.escalation_limit_myr:.0f}.
- request_info: validation says not ready — clarifications needed from employee.

`next_action` is a single sentence describing what the system or a
human should do next. `approver_role` is only set for escalations.
`confidence` is your self-estimate of the decision's correctness.
"""


@traceable(run_type="chain", name="agent.approval")
def approval_node(state: WorkflowState) -> WorkflowState:
    claim = state["intake"]
    intel = state.get("intelligence")
    policy = state.get("policy")
    validation = state.get("validation")

    user_msg = f"""Case file:

Claim: {claim.model_dump_json(indent=2)}

Intelligence: {intel.model_dump_json(indent=2) if intel else 'n/a'}

Policy: {policy.model_dump_json(indent=2) if policy else 'n/a'}

Validation: {validation.model_dump_json(indent=2) if validation else 'n/a'}

Emit the ApprovalOutcome."""

    outcome = chat_structured(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        ApprovalOutcome,
        cfg=settings.cfg_approval,
    )

    trace = state.get("trace", []) + ["approval"]
    return {**state, "approval": outcome, "trace": trace}
