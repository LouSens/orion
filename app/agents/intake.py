"""Intake Agent — unstructured → structured.

Pulls vendor, product, amount, date, justification, etc. out of the
employee's free-text message + pasted receipt. Self-reports confidence
and missing fields so downstream agents can adapt.

v2: Regex currency pre-pass runs before the LLM call to anchor the
extracted amount and flag discrepancies (anti-hallucination guard).
"""
from __future__ import annotations

from langsmith import traceable

from ..config import settings
from ..llm import chat_structured
from ..schemas import IntakeClaim
from ..state import WorkflowState
from ..tools.amount_extractor import amount_discrepancy_flag, extract_largest_amount

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
- If a RECEIPT CROSS-CHECK hint is provided, use it to validate the amount.
  If the claimed amount diverges from the receipt token by more than 20%,
  set `confidence` below 0.6 and add a note explaining the discrepancy.
"""


@traceable(run_type="chain", name="agent.intake")
def intake_node(state: WorkflowState) -> WorkflowState:
    sub = state["submission"]

    # Deterministic regex pre-pass — runs before the LLM
    regex_amount = extract_largest_amount(sub.receipt_text or "")

    # Build cross-check hint if we found a regex anchor
    cross_check_hint = ""
    if regex_amount is not None:
        cross_check_hint = (
            f"\nRECEIPT CROSS-CHECK: Regex scan found largest numeric token = {regex_amount} MYR."
        )
        # Try to extract a claimed amount from free_text for comparison
        claimed_from_text = extract_largest_amount(sub.free_text or "")
        if claimed_from_text and amount_discrepancy_flag(regex_amount, claimed_from_text):
            cross_check_hint += (
                f" This DIVERGES from the free-text amount ({claimed_from_text} MYR) by more than 20%."
                " Flag this in `notes` and set `confidence` below 0.6."
            )

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
{cross_check_hint}
Extract the structured claim now."""

    claim = chat_structured(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        IntakeClaim,
        cfg=settings.cfg_intake,
    )

    # Attach the regex anchor so policy_engine and Supervisor can use it
    claim.regex_extracted_amount = regex_amount

    return {"intake": claim, "trace": ["intake"]}
