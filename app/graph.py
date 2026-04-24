"""LangGraph workflow assembly.

This is the *adaptive* part. The graph isn't a fixed linear pipeline —
after intake → intelligence → policy, a supervisor function inspects
the current WorkflowState and decides which branch runs next. If the
intelligence agent flags a certain duplicate, we can skip validation
and head straight to approval. If validation needs more info, we route
to a `request_info` node that short-circuits to the recorder.

    intake -> intelligence -> policy -> supervisor
                                         |
                         +---------------+---------------+
                         v                               v
                    validation                       approval
                         |                               |
               +---------+---------+                     |
               v                   v                     v
         request_info          approval              recorder
               |                   |
               v                   v
           recorder            recorder
"""
from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from .agents import (
    approval_node,
    intake_node,
    intelligence_node,
    policy_node,
    recorder_node,
    validation_node,
)
from .schemas import ApprovalDecision, ApprovalOutcome
from .state import WorkflowState


def _supervisor_route(state: WorkflowState) -> Literal["validation", "approval"]:
    """Fast-path: if a blocking duplicate or blocking policy violation
    is already certain AND extraction confidence is high, skip validation."""
    intel = state.get("intelligence")
    policy = state.get("policy")
    intake = state.get("intake")
    conf = intake.confidence if intake else 0.0

    hard_block = (
        (intel and intel.recommendation == "block_duplicate")
        or (policy and not policy.compliant and any(v.severity == "block" for v in policy.violations))
    )
    if hard_block and conf >= 0.7:
        return "approval"
    return "validation"


def _post_validation_route(state: WorkflowState) -> Literal["approval", "request_info"]:
    v = state.get("validation")
    if v and not v.ready_for_decision:
        return "request_info"
    return "approval"


@traceable(run_type="chain", name="agent.request_info")
def request_info_node(state: WorkflowState) -> WorkflowState:
    """Synthesise a REQUEST_INFO approval outcome when validation needs
    more data from the employee. No LLM call — the validation agent has
    already generated the questions; we just package them as the terminal
    decision."""
    v = state["validation"]
    outcome = ApprovalOutcome(
        decision=ApprovalDecision.REQUEST_INFO,
        approver_role=None,
        reason="Clarifications required: "
               + "; ".join(c.question for c in v.clarifications),
        confidence=0.9,
        next_action="Send clarifying questions to employee and pause workflow until reply.",
    )
    trace = state.get("trace", []) + ["request_info"]
    return {**state, "approval": outcome, "trace": trace}


def build_graph():
    g = StateGraph(WorkflowState)

    g.add_node("intake", intake_node)
    g.add_node("intelligence", intelligence_node)
    g.add_node("policy", policy_node)
    g.add_node("validation", validation_node)
    g.add_node("request_info", request_info_node)
    g.add_node("approval", approval_node)
    g.add_node("recorder", recorder_node)

    g.add_edge(START, "intake")
    g.add_edge("intake", "intelligence")
    g.add_edge("intelligence", "policy")
    g.add_conditional_edges("policy", _supervisor_route, {
        "validation": "validation",
        "approval": "approval",
    })
    g.add_conditional_edges("validation", _post_validation_route, {
        "approval": "approval",
        "request_info": "request_info",
    })
    g.add_edge("request_info", "recorder")
    g.add_edge("approval", "recorder")
    g.add_edge("recorder", END)

    return g.compile()


workflow = build_graph()
