"""Shared workflow state passed between LangGraph nodes.

Every agent reads what it needs from here and writes back its structured
report. The supervisor node routes on the union of signals present —
that's what makes the engine *stateful and adaptive* instead of a fixed
pipeline.
"""
from __future__ import annotations

from typing import Optional, TypedDict

from .schemas import (
    ApprovalOutcome,
    IntakeClaim,
    IntelligenceReport,
    LedgerRecord,
    PolicyReport,
    ReimbursementSubmission,
    ValidationReport,
)


class WorkflowState(TypedDict, total=False):
    # Inputs
    claim_id: str
    submission: ReimbursementSubmission

    # Agent outputs
    intake: IntakeClaim
    intelligence: IntelligenceReport
    policy: PolicyReport
    validation: ValidationReport
    approval: ApprovalOutcome
    record: LedgerRecord

    # Control
    retry_count: int
    terminal: bool
    error: Optional[str]
    trace: list[str]  # ordered list of nodes visited — for the demo UI
