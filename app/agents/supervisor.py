"""Supervisor Agent — LLM-driven dynamic task orchestrator.

The architectural centrepiece of Orion. Receives the fully-accumulated
WorkflowState and uses an LLM call to decide which of five routing paths
to take next. A hard `supervisor_visits` counter guarantees termination —
at visit 3 the LLM is bypassed and the graph forces escalation.

Five routes:
    route_to_approval           — fast-path or clear-cut case → Critic
    route_back_to_intelligence  — intelligence report shallow/incomplete
    route_back_to_policy        — new context warrants a policy re-check
    request_human_escalation    — genuinely ambiguous; human must decide
    request_user_clarification  — missing information; return questions, end graph
"""
from __future__ import annotations

from langsmith import traceable

from ..config import settings
from ..llm import chat_structured
from ..schemas import SupervisorDecision, SupervisorRoute
from ..state import WorkflowState

SYSTEM = """You are the Supervisor Agent — the brain of an agentic expense-reimbursement workflow.

You receive the *full accumulated state* of a claim:
  • The extracted claim (from Intake) including regex_extracted_amount cross-check
  • The intelligence report (from Intelligence) with pre-computed anomaly signals
  • The policy report (from the deterministic policy engine) with hard violations,
    routing hints, and soft ambiguous flags

Your sole job: decide what happens next by choosing exactly one of these five routes:

  route_to_approval
      → Route to the Critic agent. Use for clear-cut cases: obvious approval OR
        obvious rejection (duplicate with seats, hard policy block). Also use when
        all signals are consistent and a decision is straightforward.

  route_back_to_intelligence
      → The intelligence report is shallow, missing key context, or findings feel
        inconsistent with the claim. Send it back for a deeper dig.
        Include focus_areas specifying exactly what to investigate.

  route_back_to_policy
      → New context (e.g. clarified vendor, corrected amount) suggests a different
        policy rule may apply that wasn't checked. Very fast — no LLM call.
        Include focus_areas.

  request_human_escalation
      → Genuinely ambiguous. Both approval and rejection are defensible and a
        human must decide. Reserve for true edge-cases.

  request_user_clarification
      → Critical information is missing and cannot be inferred. Terminate the graph
        and return structured questions to the employee. Populate
        clarification_questions with 1-3 specific, answerable questions.

Guidelines:
- Prefer route_to_approval over request_human_escalation when the case is clear.
- Loop-backs are expensive — only use them if the gap is material.
- If policy.fast_reject=True (hard block), route_to_approval for a clean reject.
- Use routing_hints from policy to inform the approval tier (auto/manager/finance).
- Your `reasoning` must be 2-4 sentences, justifiable to a human auditor.
- `focus_areas` only for loop-backs and clarification routes.
"""


@traceable(run_type="chain", name="agent.supervisor")
def supervisor_node(state: WorkflowState) -> WorkflowState:
    """LLM-driven routing with hard termination guard."""
    visits = state.get("supervisor_visits", 0) + 1

    # Hard termination guard — bypass LLM entirely
    if visits >= 3:
        decision = SupervisorDecision(
            route=SupervisorRoute.request_human_escalation,
            reasoning=f"Auto-escalated: supervisor_visits={visits} reached limit of 3. "
                      "Graph cannot loop indefinitely — routing to human review.",
        )
        return {
            "supervisor": decision,
            "supervisor_visits": visits,
            "trace": [f"supervisor:force_escalate(visits={visits})"],
        }

    claim = state["intake"]
    intel = state.get("intelligence")
    policy = state.get("policy")
    retry_count = state.get("retry_count", 0)

    intel_block = (
        f"- recommendation: {intel.recommendation}\n"
        f"- is_likely_duplicate: {intel.is_likely_duplicate}\n"
        f"- rationale: {intel.rationale}\n"
        f"- duplicate_matches: {len(intel.duplicate_matches)} found"
        if intel else "  (not available)"
    )
    policy_block = (
        f"- compliant: {policy.compliant}\n"
        f"- fast_reject: {policy.fast_reject}\n"
        f"- hard_violations: {[(v.rule_id, v.severity) for v in policy.hard_violations]}\n"
        f"- routing_hints: {policy.routing_hints}\n"
        f"- ambiguous_flags: {policy.ambiguous_flags}\n"
        f"- summary: {policy.summary}"
        if policy else "  (not available)"
    )

    amount_cross_check = ""
    if claim.regex_extracted_amount is not None:
        amount_cross_check = (
            f"\n- regex_extracted_amount: {claim.regex_extracted_amount} MYR "
            f"(claimed: {claim.amount_myr} MYR)"
        )

    user_msg = f"""Current workflow state (loop count: {retry_count}, supervisor visit: {visits}/3):

CLAIM:
- vendor: {claim.vendor}
- product: {claim.product}
- category: {claim.category}
- amount_myr: {claim.amount_myr}
- billing_period: {claim.billing_period}
- justification: {claim.business_justification}
- confidence: {claim.confidence}
- missing_fields: {claim.missing_fields}{amount_cross_check}

INTELLIGENCE REPORT:
{intel_block}

POLICY REPORT:
{policy_block}

Choose your route now. Loop-backs increase latency — only use them if
the gap is genuinely material. At visit 3 you will be bypassed."""

    decision = chat_structured(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        SupervisorDecision,
        cfg=settings.cfg_supervisor,
    )

    # Increment retry_count only on loop-backs
    new_retry = retry_count
    if decision.route in (
        SupervisorRoute.route_back_to_intelligence,
        SupervisorRoute.route_back_to_policy,
    ):
        new_retry += 1

    return {
        "supervisor": decision,
        "retry_count": new_retry,
        "supervisor_visits": visits,
        "trace": [f"supervisor:{decision.route.value}"],
    }
