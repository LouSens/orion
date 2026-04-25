"""Critic Agent — adversarial financial reviewer.

Tries to find the strongest reason to REJECT the claim. Only approves
when no defensible counter-argument exists. This adversarial stance is a
financial control mechanism, not a bias — every false approval costs money.

Emits the same ApprovalOutcome schema as the old Approval agent so the
Recorder node requires no changes.
"""
from __future__ import annotations

from langsmith import traceable

from ..config import settings
from ..llm import chat_structured
from ..schemas import ApprovalDecision, ApprovalOutcome
from ..state import WorkflowState

SYSTEM = f"""You are the Critic Agent — an adversarial financial reviewer.

Your job: find the **strongest possible reason to REJECT this claim**.
Search for inconsistencies, policy violations, missing evidence, amount
discrepancies, duplicate signals, or risk patterns in the accumulated reports.

Only if you **cannot construct a defensible counter-argument** should you approve.
If you can find a reason to reject or escalate, do so.

This adversarial stance is a financial control mechanism, not a bias.
Every false approval costs the company money.

Decision options: {', '.join(d.value for d in ApprovalDecision)}

Guidance:
- auto_reject: Any blocking policy violation, duplicate with seats available,
  intelligence says 'block_duplicate', amount mismatch flagged by Intake.
- auto_approve: You actively searched for a reason to reject and found none.
  Claim is clean, compliant, amount <= MYR {settings.auto_approve_limit_myr:.0f},
  intelligence says 'proceed'.
- escalate_manager: Borderline case, warn-level signals, amount MYR {settings.auto_approve_limit_myr:.0f}–{settings.escalation_limit_myr:.0f},
  or intelligence suggests an alternative. A human should decide.
- escalate_finance: Amount > MYR {settings.escalation_limit_myr:.0f}.
- request_info: Critical information is missing; cannot decide without it.

`next_action` is a single sentence describing what happens next.
`approver_role` is only set for escalations.
`confidence` is your self-estimate of decision correctness.
"""


@traceable(run_type="chain", name="agent.critic")
def critic_node(state: WorkflowState) -> WorkflowState:
    claim = state["intake"]
    intel = state.get("intelligence")
    policy = state.get("policy")

    user_msg = f"""Case file for adversarial review:

Claim: {claim.model_dump_json(indent=2)}

Intelligence: {intel.model_dump_json(indent=2) if intel else 'n/a'}

Policy: {policy.model_dump_json(indent=2) if policy else 'n/a'}

Find the strongest reason to reject. If you cannot, approve."""

    outcome = chat_structured(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        ApprovalOutcome,
        cfg=settings.cfg_approval,
    )

    return {"approval": outcome, "trace": ["critic"]}
