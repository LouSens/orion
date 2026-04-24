"""Intake Agent — unstructured → structured.

Pulls vendor, product, amount, date, justification, etc. out of the
employee's free-text message + pasted receipt. Self-reports confidence
and missing fields so downstream agents can adapt.
"""
from __future__ import annotations

from langsmith import traceable

from ..config import settings
from ..llm import chat_structured
from ..schemas import IntakeClaim
from ..state import WorkflowState

SYSTEM = """You are the Intake Agent in a subscription-reimbursement workflow.
Your job: read the employee's free-text message and attached receipt, then
extract a structured claim. Be strict about what you do and do not know —
if a value is not clearly stated, leave it null and add the field name to
`missing_fields`. Never invent amounts, vendors, or dates.

Rules:
- `amount_myr` must be in Malaysian Ringgit. If the receipt is in another
  currency, still record that in `amount_original` + `currency_original`
  and leave `amount_myr` null (a downstream step will convert).
- `confidence` is your self-estimate of overall extraction quality, not
  per-field.
- Category must be one of the enum values; if the subscription doesn't
  fit cleanly, use "other".
"""


@traceable(run_type="chain", name="agent.intake")
def intake_node(state: WorkflowState) -> WorkflowState:
    sub = state["submission"]
    user_msg = f"""Employee: {sub.employee_name} ({sub.employee_id}), team: {sub.employee_team}

Free-text submission:
---
{sub.free_text}
---

Receipt / invoice text (may be empty):
---
{sub.receipt_text or "(no receipt attached)"}
---

Attachments referenced: {sub.attachments or "none"}

Extract the structured claim now."""

    claim = chat_structured(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        IntakeClaim,
        cfg=settings.cfg_intake,
    )

    trace = state.get("trace", []) + ["intake"]
    return {**state, "intake": claim, "trace": trace}
