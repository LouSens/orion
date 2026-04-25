"""Shared workflow state passed between LangGraph nodes.

Every agent reads what it needs from here and writes back its structured
report. The supervisor node routes on the union of signals present —
that's what makes the engine *stateful and adaptive* instead of a fixed
pipeline.

Note on `trace`: uses operator.add reducer so parallel branches
(intelligence ∥ policy_check) can each append their entry without conflict.
"""
from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from .schemas import (
    ApprovalOutcome,
    IntakeClaim,
    IntelligenceReport,
    LedgerRecord,
    PolicyReport,
    ReimbursementSubmission,
    SupervisorDecision,
)


class WorkflowState(TypedDict, total=False):
    # Inputs
    claim_id: str
    submission: ReimbursementSubmission

    # Agent outputs
    intake: IntakeClaim
    intelligence: IntelligenceReport
    policy: PolicyReport
    supervisor: SupervisorDecision
    approval: ApprovalOutcome
    record: LedgerRecord

    # Control
    retry_count: int
    supervisor_visits: int  # hard termination counter — forces escalation at >= 3
    submission_hash: Optional[str]  # SHA256 fingerprint for idempotency dedup (P1.6)
    terminal: bool
    error: Optional[str]
    trace: Annotated[list[str], operator.add]  # reducer: parallel nodes each append one entry
