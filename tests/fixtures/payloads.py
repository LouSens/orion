"""Hand-curated `ReimbursementSubmission` scenarios.

Each scenario exercises a distinct routing path through the v2 graph.
Adding a new path requires a new entry here AND a new row in `expected.yaml`.
"""
from __future__ import annotations

from app.schemas import ReimbursementSubmission

PAYLOADS: dict[str, ReimbursementSubmission] = {
    "clean": ReimbursementSubmission(
        employee_id="EMP-1001",
        employee_name="Aisha Rahman",
        employee_team="Engineering",
        free_text=(
            "Please expense my Claude Pro subscription for April 2026, used "
            "daily for RFC drafting and code review. USD 20 = MYR 94.50."
        ),
        receipt_text="Anthropic — Claude Pro Monthly — $20.00 — 2026-04-10",
    ),
    "duplicate": ReimbursementSubmission(
        employee_id="E003",
        employee_name="Wei Ling",
        employee_team="Operations",
        free_text="Reimburse personal Notion Plus, MYR 250, I need it for SOPs.",
        receipt_text="Notion Labs Inc. — Notion Plus — MYR 250.00 — 2026-04-25",
    ),
    "semantic_dup": ReimbursementSubmission(
        employee_id="EMP-1003",
        employee_name="Priya Nair",
        employee_team="Marketing",
        free_text="ChatGPT Plus for campaign copywriting, MYR 96 this month.",
        receipt_text="OpenAI — ChatGPT Plus — $20 — 2026-04-15",
    ),
    "high_value": ReimbursementSubmission(
        employee_id="EMP-1004",
        employee_name="Farhan Zaki",
        employee_team="Engineering",
        free_text=(
            "Datadog Pro annual, MYR 7,800, critical for payments service "
            "observability."
        ),
        receipt_text="Datadog Inc. — Pro Annual — USD 1,656 (MYR 7,800) — 2026-04-20",
    ),
}
