"""End-to-end smoke test — invokes the graph against 5 canned scenarios
and prints a compact summary. Run: `python -m scripts.smoke`

This script mocks the ILMU LLM when ILMU_API_KEY=dev-key so the graph
can be exercised *offline* for architectural demos. In production, set a
real key and the same fixtures run against GLM-5.1.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import llm  # noqa: E402
from app.config import settings, wire_langsmith  # noqa: E402
from app.schemas import ReimbursementSubmission  # noqa: E402


SCENARIOS = {
    "clean": dict(
        employee_id="EMP-1001", employee_name="Aisha Rahman", employee_team="Engineering",
        free_text="Please expense my Claude Pro subscription for April 2026, used daily for "
                  "RFC drafting and code review. USD 20 = MYR 94.50, paid 2026-04-10.",
        receipt_text="Anthropic — Claude Pro Monthly — $20.00 — 2026-04-10",
    ),
    "duplicate": dict(
        employee_id="EMP-1002", employee_name="Wei Ling", employee_team="Operations",
        free_text="Reimburse personal Notion Plus, MYR 75, I need it for SOPs.",
        receipt_text="Notion Labs Inc. — Notion Plus — $16 (MYR 75.40) — 2026-04-18",
    ),
    "semantic_dup": dict(
        employee_id="EMP-1003", employee_name="Priya Nair", employee_team="Marketing",
        free_text="ChatGPT Plus for campaign copywriting, MYR 96 this month.",
        receipt_text="OpenAI — ChatGPT Plus — $20 — 2026-04-15",
    ),
    "high_value": dict(
        employee_id="EMP-1004", employee_name="Farhan Zaki", employee_team="Engineering",
        free_text="Datadog Pro annual, MYR 7,800, critical for payments service observability.",
        receipt_text="Datadog Inc. — Pro Annual — USD 1,656 (MYR 7,800) — 2026-04-20",
    ),
    "ambiguous": dict(
        employee_id="EMP-1005", employee_name="Iman Yusof", employee_team="AI Platform",
        free_text="expensed a thing for the project, about 200 ringgit, please process",
        receipt_text="",
    ),
}


def _install_stub_llm() -> None:
    """Deterministic canned responses keyed off the system prompt shape.
    Good enough to exercise routing without a real API key."""
    import re as _re

    def _fake(messages, schema, *, temperature=0.1, max_retries=1):
        sys_msg = messages[0]["content"] if messages else ""
        user_msg = messages[-1]["content"] if len(messages) > 1 else ""
        low = user_msg.lower()
        name = schema.__name__
        
        # Key matches off the claim's own extracted fields, not stray
        # mentions in the org catalog block. For intake, look at the
        # raw free-text + receipt area.
        m_vendor = _re.search(r"(?:^|\n)-\s*vendor:\s*(.+)", low)
        m_product = _re.search(r"(?:^|\n)-\s*product:\s*(.+)", low)
        claim_vendor = (m_vendor.group(1).strip() if m_vendor else "")
        claim_product = (m_product.group(1).strip() if m_product else "")
        claim_blob = f"{claim_vendor} {claim_product}"
        if os.environ.get("ORION_DEBUG"):
            print(f"[stub] {name} claim_blob={claim_blob!r}")
        if name == "IntakeClaim":
            if "datadog" in low:
                return schema.model_validate(dict(vendor="Datadog Inc.", product="Datadog Pro",
                    category="engineering", amount_myr=7800.0, currency_original="USD",
                    amount_original=1656.0, billing_period="annual", purchase_date="2026-04-20",
                    business_justification="Payments service observability", confidence=0.9,
                    missing_fields=[]))
            if "notion" in low:
                return schema.model_validate(dict(vendor="Notion Labs Inc.", product="Notion Plus",
                    category="productivity", amount_myr=75.4, currency_original="USD",
                    amount_original=16.0, billing_period="monthly", purchase_date="2026-04-18",
                    business_justification="Team SOPs and documentation", confidence=0.88,
                    missing_fields=[]))
            if "chatgpt" in low:
                return schema.model_validate(dict(vendor="OpenAI", product="ChatGPT Plus",
                    category="ai_tools", amount_myr=96.0, currency_original="USD",
                    amount_original=20.0, billing_period="monthly", purchase_date="2026-04-15",
                    business_justification="Campaign copy and competitive research", confidence=0.9,
                    missing_fields=[]))
            if "claude pro" in low:
                return schema.model_validate(dict(vendor="Anthropic PBC", product="Claude Pro",
                    category="ai_tools", amount_myr=94.5, currency_original="USD",
                    amount_original=20.0, billing_period="monthly", purchase_date="2026-04-10",
                    business_justification="Daily RFC drafting and code review", confidence=0.92,
                    missing_fields=[]))
            return schema.model_validate(dict(vendor=None, product=None, category=None,
                amount_myr=200.0, billing_period="unknown", business_justification=None,
                confidence=0.25, missing_fields=["vendor","product","purchase_date","business_justification"],
                notes="Free-text is extremely vague."))

        if name == "IntelligenceReport":
            if "notion plus" in low or "notion labs" in low:
                return schema.model_validate(dict(is_likely_duplicate=True,
                    duplicate_matches=[dict(existing_subscription_id="ORG-SUB-001",
                        existing_product="Notion Team Plan", owner_team="Operations",
                        similarity_score=0.95, reasoning="Same vendor, same product family; seats available.")],
                    alternatives=[dict(product="Notion Team Plan (org seat)", reason="9 free seats on org licence",
                        estimated_savings_myr=75.4, source="org_existing_license")],
                    cross_reference_notes="Organisation already pays for Notion Team with 9 seats free.",
                    recommendation="block_duplicate",
                    rationale="Employee should request a seat on ORG-SUB-001 rather than self-purchase."))
            if "chatgpt" in low or "openai" in low:
                return schema.model_validate(dict(is_likely_duplicate=True,
                    duplicate_matches=[dict(existing_subscription_id="ORG-SUB-005",
                        existing_product="ChatGPT Team", owner_team="AI Platform",
                        similarity_score=0.82, reasoning="Same vendor and overlapping capability; however ChatGPT Team licence is fully utilised.")],
                    alternatives=[dict(product="Request expansion of ChatGPT Team licence",
                        reason="No seats left on org licence; expansion is cheaper per-seat",
                        estimated_savings_myr=24.0, source="cheaper_tier")],
                    cross_reference_notes="ChatGPT Team exists (25/25 seats used). Personal Plus is a workaround but not preferred.",
                    recommendation="suggest_alternative",
                    rationale="Org licence preferred; request seat expansion."))
            if "datadog" in low:
                return schema.model_validate(dict(is_likely_duplicate=False,
                    alternatives=[], cross_reference_notes="Not on approved catalog — requires finance review for first-time vendor.",
                    recommendation="proceed", rationale="No overlap with existing org tooling."))
            if "claude pro" in low:
                return schema.model_validate(dict(is_likely_duplicate=False,
                    alternatives=[], cross_reference_notes="Claude Pro is on the approved catalog for individual claims up to MYR 120/month.",
                    recommendation="proceed", rationale="Within approved catalog; no org duplicate."))
            return schema.model_validate(dict(is_likely_duplicate=False,
                alternatives=[], cross_reference_notes="Insufficient data to cross-reference.",
                recommendation="proceed", rationale="Defer to validation."))

        if name == "PolicyReport":
            cb = claim_blob
            intel_dup = "is_likely_duplicate: true" in low and "block_duplicate" in low
            if intel_dup:
                return schema.model_validate(dict(compliant=False,
                    applied_rules=["POL-004","POL-005","POL-006","POL-007"],
                    violations=[dict(rule_id="POL-006",
                        description="Duplicate of an existing org licence with seats available.",
                        severity="block")],
                    summary="Blocked by POL-006 — employee should request a seat on the existing org licence."))
            if "datadog" in cb or "7800" in cb:
                return schema.model_validate(dict(compliant=True,
                    applied_rules=["POL-003","POL-004","POL-005","POL-007","POL-008"],
                    violations=[], summary="Compliant, but above MYR 5000 — finance escalation required."))
            if "chatgpt" in cb or "openai" in cb:
                return schema.model_validate(dict(compliant=True,
                    applied_rules=["POL-001","POL-004","POL-005","POL-006"],
                    violations=[dict(rule_id="POL-008",
                        description="Consider requesting org-licence seat expansion (warn).",
                        severity="warn")],
                    summary="Compliant overall; intelligence suggests alternative."))
            if "ambiguous" in low or "about 200" in low or "expensed a thing" in low or not cb.strip():
                return schema.model_validate(dict(compliant=False,
                    applied_rules=["POL-004","POL-005"],
                    violations=[dict(rule_id="POL-004",
                        description="Missing business justification.",severity="block"),
                        dict(rule_id="POL-005",
                        description="Category unknown — cannot verify approved category.",severity="block")],
                    summary="Cannot evaluate; request clarification."))
            return schema.model_validate(dict(compliant=True,
                applied_rules=["POL-001","POL-004","POL-005","POL-007"],
                violations=[], summary="Compliant, within auto-approve threshold."))

        if name == "ValidationReport":
            if "expensed a thing" in low or "missing_fields: ['vendor'" in low:
                return schema.model_validate(dict(ready_for_decision=False,
                    clarifications=[
                        dict(field="vendor", question="Which vendor did you purchase from?"),
                        dict(field="product", question="Which specific product/plan was this?"),
                        dict(field="business_justification", question="What is the business justification?")],
                    summary="Critical fields missing; need employee input before deciding."))
            return schema.model_validate(dict(ready_for_decision=True,
                clarifications=[], summary="All required fields present; proceed to approval."))

        if name == "ApprovalOutcome":
            from app.schemas import ApprovalDecision
            cb = claim_blob
            if "7800" in low or "datadog" in cb:
                return schema.model_validate(dict(decision=ApprovalDecision.ESCALATE_FINANCE.value,
                    approver_role="finance_controller",
                    reason="Amount MYR 7800 exceeds finance threshold; first-time vendor.",
                    confidence=0.93,
                    next_action="Route to finance controller with vendor-onboarding packet."))
            if '"recommendation": "block_duplicate"' in low:
                return schema.model_validate(dict(decision=ApprovalDecision.AUTO_REJECT.value,
                    approver_role=None,
                    reason="Duplicate of existing org licence with seats available.",
                    confidence=0.95,
                    next_action="Reply to employee with link to request a seat on the existing org licence."))
            if '"recommendation": "suggest_alternative"' in low:
                return schema.model_validate(dict(decision=ApprovalDecision.ESCALATE_MANAGER.value,
                    approver_role="direct_manager",
                    reason="Intelligence suggests requesting org licence expansion.",
                    confidence=0.8,
                    next_action="Manager to decide between reimbursement vs. licence expansion."))
            return schema.model_validate(dict(decision=ApprovalDecision.AUTO_APPROVE.value,
                approver_role=None,
                reason="Compliant, within threshold, no duplicates.",
                confidence=0.9,
                next_action="Reimburse via next payroll cycle."))

        raise RuntimeError(f"Unhandled schema in stub: {name}")

    llm.chat_structured = _fake  # type: ignore[assignment]


def main() -> None:
    if settings.ilmu_api_key in ("", "dev-key", "replace-me"):
        print("No real ILMU key — installing deterministic stub LLM.\n")
        _install_stub_llm()
    wire_langsmith()

    from app.graph import build_graph
    graph = build_graph()

    for name, kwargs in SCENARIOS.items():
        print(f"\n{'='*70}\nSCENARIO: {name}\n{'='*70}")
        sub = ReimbursementSubmission(**kwargs)
        final = graph.invoke({
            "claim_id": f"CLM-TEST-{name.upper()}",
            "submission": sub,
            "trace": [], "retry_count": 0, "terminal": False, "error": None,
        })
        print(f"trace         : {' -> '.join(final['trace'])}")
        if final.get("intelligence"):
            print(f"intelligence  : {final['intelligence'].recommendation} "
                  f"(dup={final['intelligence'].is_likely_duplicate})")
        if final.get("policy"):
            print(f"policy        : compliant={final['policy'].compliant}, "
                  f"violations={[v.rule_id for v in final['policy'].violations]}")
        if final.get("approval"):
            print(f"decision      : {final['approval'].decision} — {final['approval'].reason}")


if __name__ == "__main__":
    main()
