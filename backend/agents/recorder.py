"""Recorder Agent — persist + notify.

Writes the decision to the ledger. In a real deployment this is where
a Notion MCP call, Slack webhook, or email-send lives. Kept here as
deterministic Python (no LLM) — the reasoning is already done; this is
just the *effectful output* stage of the workflow.
"""
from __future__ import annotations

from datetime import datetime, timezone

from langsmith import traceable

from ..schemas import ApprovalDecision, LedgerRecord
from ..state import WorkflowState
from ..tools import Ledger

_ledger = Ledger()


def _notify_list(decision: ApprovalDecision, employee_id: str) -> list[str]:
    base = [f"employee:{employee_id}"]
    if decision == ApprovalDecision.ESCALATE_MANAGER:
        base.append("role:direct_manager")
    elif decision == ApprovalDecision.ESCALATE_FINANCE:
        base.append("role:finance_controller")
    elif decision == ApprovalDecision.AUTO_APPROVE:
        base.append("role:finance_ops")
    return base


@traceable(run_type="chain", name="agent.recorder")
def recorder_node(state: WorkflowState) -> WorkflowState:
    approval = state["approval"]
    claim = state["intake"]
    submission = state["submission"]

    record = LedgerRecord(
        claim_id=state["claim_id"],
        employee_id=submission.employee_id,
        vendor=claim.vendor or "(unknown)",
        product=claim.product or "(unknown)",
        amount_myr=claim.amount_myr or 0.0,
        decision=approval.decision,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        notification_sent_to=_notify_list(approval.decision, submission.employee_id),
        submission_hash=state.get("submission_hash"),  # P1.6 idempotency fingerprint
    )
    _ledger.append(record.model_dump(mode="json"))

    return {"record": record, "terminal": True, "trace": ["recorder"]}
