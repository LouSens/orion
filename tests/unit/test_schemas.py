"""Schema validation contracts.

Requirement: R2 — every agent transition is gated on a structured pydantic
output. These tests pin the contracts so a careless schema rename can't pass
review unnoticed.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    ApprovalDecision,
    ApprovalOutcome,
    IntakeClaim,
    IntelligenceReport,
    PolicyReport,
    PolicyViolation,
    ReimbursementSubmission,
    SupervisorDecision,
    SupervisorRoute,
)


class TestIntakeClaim:
    def test_minimum_fields_validate(self) -> None:
        # Every field is optional except confidence; an empty claim is legal.
        claim = IntakeClaim()
        assert claim.confidence == 0.5
        assert claim.missing_fields == []

    def test_amount_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            IntakeClaim(amount_myr=-10)

    def test_confidence_bounded_0_to_1(self) -> None:
        with pytest.raises(ValidationError):
            IntakeClaim(confidence=1.2)

    def test_category_is_constrained_literal(self) -> None:
        with pytest.raises(ValidationError):
            IntakeClaim(category="unknown")  # type: ignore[arg-type]


class TestSupervisorDecision:
    def test_all_five_routes_are_acceptable(self) -> None:
        for route in SupervisorRoute:
            d = SupervisorDecision(route=route, reasoning="ok")
            assert d.route == route

    def test_reasoning_is_required(self) -> None:
        with pytest.raises(ValidationError):
            SupervisorDecision(route=SupervisorRoute.route_to_approval)  # type: ignore[call-arg]

    def test_route_must_be_known_value(self) -> None:
        with pytest.raises(ValidationError):
            SupervisorDecision(route="invent_route", reasoning="x")  # type: ignore[arg-type]


class TestApprovalOutcome:
    def test_all_decisions_are_acceptable(self) -> None:
        for d in ApprovalDecision:
            ApprovalOutcome(
                decision=d, reason="ok", confidence=0.5, next_action="next",
            )

    def test_confidence_bounded(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalOutcome(
                decision=ApprovalDecision.AUTO_APPROVE,
                reason="ok", confidence=2.0, next_action="next",
            )


class TestPolicyReport:
    def test_compliant_with_no_violations(self) -> None:
        r = PolicyReport(compliant=True, applied_rules=["AMT-TIER"], summary="ok")
        assert r.violations == []
        assert r.fast_reject is False

    def test_violation_severity_constrained(self) -> None:
        with pytest.raises(ValidationError):
            PolicyViolation(rule_id="POL-X", description="x", severity="critical")  # type: ignore[arg-type]


class TestIntelligenceReport:
    def test_recommendation_must_be_one_of_three(self) -> None:
        with pytest.raises(ValidationError):
            IntelligenceReport(
                is_likely_duplicate=False,
                recommendation="ignore",  # type: ignore[arg-type]
                rationale="x",
            )


class TestReimbursementSubmission:
    def test_employee_id_and_free_text_required(self) -> None:
        with pytest.raises(ValidationError):
            ReimbursementSubmission(
                employee_name="x", employee_team="x", free_text="x"
            )  # type: ignore[call-arg]
