"""End-to-end smoke test — invokes the v2 graph against 5 canned scenarios
and prints a compact summary. Run: `python -m scripts.smoke`

This script mocks the ILMU LLM when ILMU_API_KEY=dev-key so the graph
can be exercised *offline* for architectural demos. In production, set a
real key and the same fixtures run against GLM-5.1.

v2 graph shape: intake → [intelligence ∥ policy_check] → merge → supervisor → critic → recorder
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
        employee_id="E003", employee_name="Wei Ling", employee_team="Operations",
        free_text="Reimburse personal Notion Plus, MYR 250, I need it for SOPs.",
        receipt_text="Notion Labs Inc. — Notion Plus — MYR 250.00 — 2026-04-25",
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
    "uber_spike": dict(
        employee_id="E007", employee_name="Hafiz Ismail", employee_team="Operations",
        free_text="Grab ride to client meeting MYR 23. Business trip.",
        receipt_text="Grab — Business Ride — RM 23.00 — 2026-04-25",
    ),
}


def _install_stub_llm() -> None:
    """Deterministic canned responses keyed off the system prompt shape.
    Good enough to exercise routing without a real API key.
    Note: policy_check_node is deterministic Python — no stub needed for it."""
    import re as _re

    def _fake(messages, schema, *, temperature=0.1, max_retries=1, cfg=None):
        full_text = " ".join(m.get("content", "") for m in messages if isinstance(m, dict))
        # Exclude system message — it contains keywords like "block_duplicate" that would false-positive
        user_text = " ".join(m.get("content", "") for m in messages if isinstance(m, dict) and m.get("role") != "system")
        full_low = user_text.lower()
        # Scope vendor/product matching to the "Extracted claim:" section to avoid
        # org catalog false-positives (the catalog always mentions many vendors)
        claim_section_m = _re.search(r"extracted claim:(.*?)(?:\n\n|\Z)", full_text, _re.IGNORECASE | _re.DOTALL)
        claim_section = (claim_section_m.group(1) if claim_section_m else full_text).lower()
        name = schema.__name__

        m_vendor = _re.search(r"(?:^|\n)-\s*vendor:\s*(.+)", claim_section)
        m_product = _re.search(r"(?:^|\n)-\s*product:\s*(.+)", claim_section)
        claim_vendor = (m_vendor.group(1).strip() if m_vendor else "")
        claim_product = (m_product.group(1).strip() if m_product else "")
        claim_blob = f"{claim_vendor} {claim_product}"
        # For vendor/product checks use claim_section; for downstream agent checks use full_low
        low = claim_section
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
                    category="productivity", amount_myr=250.0, currency_original="MYR",
                    amount_original=250.0, billing_period="monthly", purchase_date="2026-04-25",
                    business_justification="Team SOPs and documentation", confidence=0.9,
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
            if "grab" in low:
                return schema.model_validate(dict(vendor="Grab", product="Grab Business Ride",
                    category="productivity", amount_myr=23.0, currency_original="MYR",
                    amount_original=23.0, billing_period="one_time", purchase_date="2026-04-25",
                    business_justification="Business trip to client meeting", confidence=0.9,
                    missing_fields=[]))
            return schema.model_validate(dict(vendor=None, product=None, category=None,
                amount_myr=200.0, billing_period="unknown", business_justification=None,
                confidence=0.25, missing_fields=["vendor", "product", "purchase_date", "business_justification"],
                notes="Free-text is extremely vague."))

        if name == "IntelligenceReport":
            if "notion plus" in low or "notion labs" in low:
                return schema.model_validate(dict(is_likely_duplicate=True,
                    duplicate_matches=[dict(existing_subscription_id="ORG-SUB-001",
                        existing_product="Notion Team Plan", owner_team="Operations",
                        similarity_score=0.95, reasoning="Same vendor, same product family; seats available.")],
                    alternatives=[dict(product="Notion Team Plan (org seat)", reason="9 free seats on org licence",
                        estimated_savings_myr=250.0, source="org_existing_license")],
                    cross_reference_notes="Organisation already pays for Notion Team with 9 seats free. Employee E003 has claimed Notion Plus 6 times in 6 months (employee_claim_count=6). vendor_signals show recurring_pattern_detected=True with avg interval 30 days.",
                    recommendation="block_duplicate",
                    rationale="Employee should request a seat on ORG-SUB-001 rather than self-purchase. Tools show 6 prior claims by this employee at Notion Labs."))
            if "chatgpt" in low or "openai" in low:
                return schema.model_validate(dict(is_likely_duplicate=True,
                    duplicate_matches=[dict(existing_subscription_id="ORG-SUB-005",
                        existing_product="ChatGPT Team", owner_team="AI Platform",
                        similarity_score=0.82, reasoning="Same vendor and overlapping capability; however ChatGPT Team is fully utilised.")],
                    alternatives=[dict(product="Request expansion of ChatGPT Team licence",
                        reason="No seats left on org licence; expansion is cheaper per-seat",
                        estimated_savings_myr=24.0, source="cheaper_tier")],
                    cross_reference_notes="ChatGPT Team exists (25/25 seats used). Personal Plus is a workaround.",
                    recommendation="suggest_alternative",
                    rationale="Org licence preferred; request seat expansion."))
            if "datadog" in low:
                return schema.model_validate(dict(is_likely_duplicate=False,
                    alternatives=[], cross_reference_notes="Not on approved catalog — requires finance review.",
                    recommendation="proceed", rationale="No overlap with existing org tooling."))
            if "claude pro" in low:
                return schema.model_validate(dict(is_likely_duplicate=False,
                    alternatives=[], cross_reference_notes="Claude Pro is on the approved catalog for individual claims up to MYR 120/month.",
                    recommendation="proceed", rationale="Within approved catalog; no org duplicate."))
            if "grab" in low:
                return schema.model_validate(dict(is_likely_duplicate=False,
                    alternatives=[], cross_reference_notes="E007 has 4 Grab rides this week (2026-W17) vs historical average of 1/week. anomaly_signals: spike_detected=True, z_score=3.2, current_week_count=4.",
                    recommendation="proceed", rationale="Ride itself is legitimate but frequency spike is anomalous — LLM narrates z_score=3.2."))
            return schema.model_validate(dict(is_likely_duplicate=False,
                alternatives=[], cross_reference_notes="Insufficient data to cross-reference.",
                recommendation="proceed", rationale="Defer to Supervisor."))

        if name == "SupervisorDecision":
            from app.schemas import SupervisorRoute
            intel_dup = "block_duplicate" in full_low
            intel_alt = "suggest_alternative" in full_low
            fast_rej = "fast_reject: true" in full_low
            spike = "spike_detected=true" in full_low or "z_score=3.2" in full_low
            if fast_rej:
                return schema.model_validate(dict(
                    route=SupervisorRoute.route_to_approval.value,
                    reasoning="Policy engine issued fast_reject — hard block violation. Routing to Critic for auto_reject.",
                    focus_areas=[]))
            if intel_dup:
                return schema.model_validate(dict(
                    route=SupervisorRoute.route_to_approval.value,
                    reasoning="Intelligence confirmed duplicate with available seats. Clear reject path.",
                    focus_areas=[]))
            if intel_alt:
                return schema.model_validate(dict(
                    route=SupervisorRoute.route_to_approval.value,
                    reasoning="Intelligence suggests org licence expansion preferred. Route to Critic for manager escalation.",
                    focus_areas=[]))
            if spike:
                return schema.model_validate(dict(
                    route=SupervisorRoute.route_to_approval.value,
                    reasoning="Intelligence detected anomalous Grab claim frequency (z_score=3.2). Routing to Critic for manager escalation.",
                    focus_areas=["anomaly_signals", "grab_ride_frequency"]))
            if "7800" in low or "datadog" in low:
                return schema.model_validate(dict(
                    route=SupervisorRoute.route_to_approval.value,
                    reasoning="Amount MYR 7800 exceeds finance escalation threshold. Clear path.",
                    focus_areas=[]))
            return schema.model_validate(dict(
                route=SupervisorRoute.route_to_approval.value,
                reasoning="Clean claim with no red flags. Route to Critic.",
                focus_areas=[]))

        if name == "ApprovalOutcome":
            from app.schemas import ApprovalDecision
            if "7800" in full_low or "datadog" in claim_blob:
                return schema.model_validate(dict(decision=ApprovalDecision.ESCALATE_FINANCE.value,
                    approver_role="finance_controller",
                    reason="Amount MYR 7800 exceeds finance threshold.",
                    confidence=0.93,
                    next_action="Route to finance controller with vendor-onboarding packet."))
            if "block_duplicate" in full_low or "employee_claim_count=6" in full_low:
                return schema.model_validate(dict(decision=ApprovalDecision.AUTO_REJECT.value,
                    approver_role=None,
                    reason="Duplicate of existing org licence — employee has claimed 6 times at Notion. Org seats available.",
                    confidence=0.97,
                    next_action="Request seat on ORG-SUB-001 instead."))
            if "suggest_alternative" in full_low:
                return schema.model_validate(dict(decision=ApprovalDecision.ESCALATE_MANAGER.value,
                    approver_role="direct_manager",
                    reason="Org licence preferred; request seat expansion from IT.",
                    confidence=0.8,
                    next_action="Manager to decide between reimbursement vs. licence expansion."))
            if "z_score=3.2" in full_low or "spike_detected=true" in full_low:
                return schema.model_validate(dict(decision=ApprovalDecision.ESCALATE_MANAGER.value,
                    approver_role="direct_manager",
                    reason="Anomalous claim frequency detected (4 Grab rides in one week vs. 1/month baseline, z_score=3.2).",
                    confidence=0.85,
                    next_action="Manager to verify business trips before approval."))
            return schema.model_validate(dict(decision=ApprovalDecision.AUTO_APPROVE.value,
                approver_role=None,
                reason="Compliant, within threshold, no duplicates, no anomaly signals.",
                confidence=0.9,
                next_action="Reimburse via next payroll cycle."))

        raise RuntimeError(f"Unhandled schema in stub: {name}")

    def _fake_chat(messages, *, temperature=0.1, max_tokens=2000, response_format_json=False):
        """Stub for the raw chat call used in intelligence tool loop — signal done immediately."""
        return '{"done": true}'

    llm.chat = _fake_chat  # type: ignore[assignment]
    llm.chat_structured = _fake  # type: ignore[assignment]


def main() -> None:
    if settings.ilmu_api_key in ("", "dev-key", "replace-me"):
        print("No real ILMU key — installing deterministic stub LLM.\n")
        _install_stub_llm()
    # Suppress LangSmith tracing in smoke — avoids 403 noise when key is stale.
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    wire_langsmith()

    from app.graph import build_graph
    graph = build_graph()

    for name, kwargs in SCENARIOS.items():
        print(f"\n{'='*70}\nSCENARIO: {name}\n{'='*70}")
        sub = ReimbursementSubmission(**kwargs)
        final = graph.invoke({
            "claim_id": f"CLM-TEST-{name.upper()}",
            "submission": sub,
            "trace": [], "retry_count": 0, "supervisor_visits": 0,
            "terminal": False, "error": None,
        })
        print(f"trace         : {' -> '.join(final['trace'])}")
        if final.get("intelligence"):
            print(f"intelligence  : {final['intelligence'].recommendation} "
                  f"(dup={final['intelligence'].is_likely_duplicate})")
        if final.get("policy"):
            p = final["policy"]
            print(f"policy_check  : fast_reject={p.fast_reject}, "
                  f"violations={[v.rule_id for v in p.hard_violations]}, "
                  f"hints={p.routing_hints}")
        if final.get("approval"):
            print(f"decision      : {final['approval'].decision} — {final['approval'].reason[:80]}")


if __name__ == "__main__":
    main()
