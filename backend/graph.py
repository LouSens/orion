"""LangGraph workflow assembly — v2 parallel multi-agent orchestration.

Graph topology (v2):

    START → intake → [intelligence ∥ policy_check] → merge_intel_policy
                           ▲                                  │
                           │ route_back_intel      fast_reject │ (hard block)
                           │                                  ▼
                           │                           ┌── critic
                           │                           │
                           └── supervisor ─────────────┤
                                    │                  │
                          5 routes: │  route_to_approval → critic
                                    │  route_back_to_intelligence → intelligence
                                    │  route_back_to_policy → policy_check
                                    │  request_human_escalation → escalate
                                    │  request_user_clarification → clarify
                                    │
                critic ──────────────┐
                clarify ─────────────┤──► recorder → END
                escalate ────────────┘

Loop guard: supervisor_visits >= 3 forces request_human_escalation before any LLM call.
Fast-reject: policy.fast_reject=True routes directly to critic, bypassing Supervisor.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from .agents import (
    critic_node,
    intake_node,
    intelligence_node,
    recorder_node,
    supervisor_node,
)
from .schemas import (
    ApprovalDecision,
    ApprovalOutcome,
    PolicyReport,
    PolicyViolation,
    SupervisorRoute,
)
from .state import WorkflowState
from .tools.policy_engine import evaluate_hard_rules
from .tools.policy_store import PolicyStore

_store = PolicyStore()


# ---------------------------------------------------------------------------
# Inline graph nodes (no LLM — pure state packaging)
# ---------------------------------------------------------------------------

@traceable(run_type="chain", name="agent.policy_check")
def policy_check_node(state: WorkflowState) -> WorkflowState:
    """Deterministic hard-rule policy evaluation — zero LLM calls."""
    claim = state["intake"]
    receipt_text = state["submission"].receipt_text

    # POL-006 is NOT evaluated here — it's reconciled in merge_intel_policy_node
    # after the parallel Intelligence branch completes.
    result = evaluate_hard_rules(claim, receipt_text, is_likely_duplicate=False)

    policy_report = PolicyReport(
        compliant=not result.fast_reject,
        applied_rules=_store.automatic_rule_ids() + ["AMT-TIER"],
        violations=result.hard_violations,
        hard_violations=result.hard_violations,
        routing_hints=result.routing_hints,
        ambiguous_flags=result.ambiguous_flags,
        fast_reject=result.fast_reject,
        summary=(
            f"{'FAST REJECT' if result.fast_reject else 'No hard violations'}. "
            f"{len(result.hard_violations)} block violation(s). "
            f"{len(result.ambiguous_flags)} soft flag(s) for Supervisor."
        ),
    )
    return {"policy": policy_report, "trace": [f"policy_check(violations={len(result.hard_violations)})"]}


@traceable(run_type="chain", name="agent.merge")
def merge_intel_policy_node(state: WorkflowState) -> WorkflowState:
    """Fan-in passthrough: reconcile POL-006 after parallel branches complete."""
    intel = state.get("intelligence")
    policy = state.get("policy")

    updates: dict = {}
    if intel and intel.is_likely_duplicate and policy:
        already_flagged = any(v.rule_id == "POL-006" for v in policy.hard_violations)
        if not already_flagged:
            # Return a new PolicyReport with the appended flag (immutable update)
            new_flags = list(policy.ambiguous_flags) + [
                "POL-006: duplicate_subscription_suspected — see intelligence.duplicate_matches"
            ]
            updates["policy"] = policy.model_copy(update={"ambiguous_flags": new_flags})
    return updates


@traceable(run_type="chain", name="agent.clarify")
def clarify_node(state: WorkflowState) -> WorkflowState:
    """Package Supervisor's clarification questions as a REQUEST_INFO terminal outcome."""
    sup = state.get("supervisor")
    questions = sup.clarification_questions if sup else []
    outcome = ApprovalOutcome(
        decision=ApprovalDecision.REQUEST_INFO,
        approver_role=None,
        reason="Clarifications required before a decision can be made.",
        confidence=0.9,
        next_action="Questions: " + " | ".join(questions) if questions else "Please provide missing information.",
    )
    return {"approval": outcome, "trace": ["clarify"]}


@traceable(run_type="chain", name="agent.escalate")
def escalate_node(state: WorkflowState) -> WorkflowState:
    """Terminal node for Supervisor-triggered human escalation."""
    sup = state.get("supervisor")
    reasoning = sup.reasoning if sup else "Supervisor flagged for human review."
    outcome = ApprovalOutcome(
        decision=ApprovalDecision.ESCALATE_MANAGER,
        approver_role="human_reviewer",
        reason=f"Human escalation requested: {reasoning}",
        confidence=1.0,
        next_action="Route to human reviewer queue for manual assessment.",
    )
    return {"approval": outcome, "trace": ["escalate"]}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _fast_reject_route(state: WorkflowState) -> str:
    """After merge: short-circuit to critic if a hard policy block fired."""
    policy = state.get("policy")
    if policy and policy.fast_reject:
        return "critic"
    return "supervisor"


def _supervisor_route(state: WorkflowState) -> str:
    """Translate the Supervisor's decision into a graph edge."""
    sup = state.get("supervisor")
    if sup is None:
        return "escalate"

    route_map = {
        SupervisorRoute.route_to_approval:           "critic",
        SupervisorRoute.route_back_to_intelligence:  "intelligence",
        SupervisorRoute.route_back_to_policy:        "policy_check",
        SupervisorRoute.request_human_escalation:    "escalate",
        SupervisorRoute.request_user_clarification:  "clarify",
    }
    return route_map.get(sup.route, "escalate")


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph():
    g = StateGraph(WorkflowState)

    # --- Nodes ---
    g.add_node("intake", intake_node)
    g.add_node("intelligence", intelligence_node)
    g.add_node("policy_check", policy_check_node)
    g.add_node("merge_intel_policy", merge_intel_policy_node)
    g.add_node("supervisor", supervisor_node)
    g.add_node("critic", critic_node)
    g.add_node("clarify", clarify_node)
    g.add_node("escalate", escalate_node)
    g.add_node("recorder", recorder_node)

    # --- Parallel branches after intake ---
    g.add_edge(START, "intake")
    g.add_edge("intake", "intelligence")      # branch 1
    g.add_edge("intake", "policy_check")      # branch 2 (runs in parallel)
    g.add_edge("intelligence", "merge_intel_policy")
    g.add_edge("policy_check", "merge_intel_policy")

    # --- Fast-reject short-circuit or normal path to Supervisor ---
    g.add_conditional_edges(
        "merge_intel_policy",
        _fast_reject_route,
        {"critic": "critic", "supervisor": "supervisor"},
    )

    # --- Supervisor 5-way routing ---
    g.add_conditional_edges(
        "supervisor",
        _supervisor_route,
        {
            "critic": "critic",
            "intelligence": "intelligence",   # loop-back
            "policy_check": "policy_check",   # loop-back (fast — deterministic)
            "escalate": "escalate",
            "clarify": "clarify",
        },
    )

    # --- All terminal paths → Recorder → END ---
    g.add_edge("critic", "recorder")
    g.add_edge("clarify", "recorder")
    g.add_edge("escalate", "recorder")
    g.add_edge("recorder", END)

    return g.compile()


workflow = build_graph()
