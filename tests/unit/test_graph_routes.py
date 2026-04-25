"""Unit tests for the graph's routing functions and non-LLM nodes.

Requirement: R3 — adaptive routing logic in app/graph.py.
Modules under test: app/graph.py (`_fast_reject_route`, `_supervisor_route`,
`clarify_node`, `escalate_node`, `merge_intel_policy_node`).

These are pure functions over WorkflowState — no LLM, no I/O.
"""
from __future__ import annotations

from app.graph import (
    _fast_reject_route,
    _supervisor_route,
    clarify_node,
    escalate_node,
    merge_intel_policy_node,
)
from app.schemas import (
    ApprovalDecision,
    IntelligenceReport,
    PolicyReport,
    SupervisorDecision,
    SupervisorRoute,
)


def _policy(*, fast_reject: bool = False) -> PolicyReport:
    return PolicyReport(
        compliant=not fast_reject,
        applied_rules=[],
        summary="test",
        fast_reject=fast_reject,
    )


def _intel(*, is_dup: bool = False) -> IntelligenceReport:
    return IntelligenceReport(
        is_likely_duplicate=is_dup,
        recommendation="block_duplicate" if is_dup else "proceed",
        rationale="test",
    )


class TestFastRejectRoute:
    def test_routes_to_critic_on_fast_reject(self) -> None:
        state = {"policy": _policy(fast_reject=True)}
        assert _fast_reject_route(state) == "critic"  # type: ignore[arg-type]

    def test_routes_to_supervisor_when_compliant(self) -> None:
        state = {"policy": _policy(fast_reject=False)}
        assert _fast_reject_route(state) == "supervisor"  # type: ignore[arg-type]

    def test_routes_to_supervisor_when_policy_missing(self) -> None:
        # Defensive default: no policy → supervisor must still get a chance.
        assert _fast_reject_route({}) == "supervisor"  # type: ignore[arg-type]


class TestSupervisorRoute:
    def test_each_supervisor_route_maps_correctly(self) -> None:
        cases = [
            (SupervisorRoute.route_to_approval, "critic"),
            (SupervisorRoute.route_back_to_intelligence, "intelligence"),
            (SupervisorRoute.route_back_to_policy, "policy_check"),
            (SupervisorRoute.request_human_escalation, "escalate"),
            (SupervisorRoute.request_user_clarification, "clarify"),
        ]
        for route, expected_edge in cases:
            state = {"supervisor": SupervisorDecision(route=route, reasoning="x")}
            assert _supervisor_route(state) == expected_edge  # type: ignore[arg-type]

    def test_missing_supervisor_falls_back_to_escalate(self) -> None:
        # Defensive: no decision in state → human review (don't silently drop).
        assert _supervisor_route({}) == "escalate"  # type: ignore[arg-type]


class TestClarifyNode:
    def test_emits_request_info_with_questions(self) -> None:
        sup = SupervisorDecision(
            route=SupervisorRoute.request_user_clarification,
            reasoning="missing data",
            clarification_questions=["What was the vendor?", "How much in MYR?"],
        )
        state = {"supervisor": sup}
        out = clarify_node(state)  # type: ignore[arg-type]
        assert out["approval"].decision == ApprovalDecision.REQUEST_INFO
        assert "What was the vendor?" in out["approval"].next_action
        assert out["trace"] == ["clarify"]

    def test_handles_missing_supervisor_gracefully(self) -> None:
        out = clarify_node({})  # type: ignore[arg-type]
        assert out["approval"].decision == ApprovalDecision.REQUEST_INFO


class TestEscalateNode:
    def test_emits_escalate_manager(self) -> None:
        sup = SupervisorDecision(
            route=SupervisorRoute.request_human_escalation,
            reasoning="Two defensible decisions exist.",
        )
        out = escalate_node({"supervisor": sup})  # type: ignore[arg-type]
        assert out["approval"].decision == ApprovalDecision.ESCALATE_MANAGER
        assert out["approval"].approver_role == "human_reviewer"
        assert "defensible" in out["approval"].reason

    def test_handles_missing_supervisor(self) -> None:
        out = escalate_node({})  # type: ignore[arg-type]
        assert out["approval"].decision == ApprovalDecision.ESCALATE_MANAGER


class TestMergeIntelPolicyNode:
    def test_appends_pol006_when_intel_dup_and_not_already_flagged(self) -> None:
        state = {
            "intelligence": _intel(is_dup=True),
            "policy": _policy(fast_reject=False),
        }
        out = merge_intel_policy_node(state)  # type: ignore[arg-type]
        flags = out["policy"].ambiguous_flags
        assert any("POL-006" in f for f in flags)

    def test_no_op_when_intel_not_dup(self) -> None:
        state = {
            "intelligence": _intel(is_dup=False),
            "policy": _policy(),
        }
        out = merge_intel_policy_node(state)  # type: ignore[arg-type]
        # Empty dict means "no updates" in LangGraph's reducer protocol.
        assert out == {}

    def test_no_op_when_policy_missing(self) -> None:
        state = {"intelligence": _intel(is_dup=True)}
        assert merge_intel_policy_node(state) == {}  # type: ignore[arg-type]
