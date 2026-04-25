"""Unit tests for the deterministic policy engine.

Requirement: R3 — adaptive routing depends on hard-rule signals.
Module under test: app/tools/policy_engine.py
"""
from __future__ import annotations

import pytest

from app.schemas import IntakeClaim
from app.tools.policy_engine import evaluate_hard_rules


def _claim(**overrides) -> IntakeClaim:
    """Build an IntakeClaim with sensible defaults — overrides win."""
    base: dict = dict(
        vendor="Notion Labs",
        product="Notion Plus",
        category="productivity",
        amount_myr=250.0,
        billing_period="monthly",
        business_justification="Team SOPs and documentation",
        confidence=0.9,
    )
    base.update(overrides)
    return IntakeClaim(**base)


class TestRoutingTier:
    def test_low_amount_eligible_for_auto_approve(self) -> None:
        result = evaluate_hard_rules(_claim(amount_myr=100), receipt_text="Vendor receipt — total MYR 250.00")
        assert "auto_approve_eligible" in result.routing_hints

    def test_mid_amount_needs_manager(self) -> None:
        result = evaluate_hard_rules(_claim(amount_myr=2000), receipt_text="Vendor receipt — total MYR 250.00")
        assert "manager_approval_required" in result.routing_hints

    def test_high_amount_needs_finance(self) -> None:
        result = evaluate_hard_rules(_claim(amount_myr=7800), receipt_text="Vendor receipt — total MYR 250.00")
        assert "finance_approval_required" in result.routing_hints


class TestHardViolations:
    def test_short_justification_violates_pol004(self) -> None:
        result = evaluate_hard_rules(
            _claim(business_justification="too short"),
            receipt_text="Vendor receipt — total MYR 250.00",
        )
        assert any(v.rule_id == "POL-004" for v in result.hard_violations)

    def test_missing_receipt_above_floor_violates_pol007(self) -> None:
        result = evaluate_hard_rules(_claim(amount_myr=500), receipt_text=None)
        assert any(v.rule_id == "POL-007" for v in result.hard_violations)

    def test_under_floor_no_receipt_required(self) -> None:
        # MYR 50 is below the receipt floor of 100.
        result = evaluate_hard_rules(_claim(amount_myr=50), receipt_text=None)
        assert not any(v.rule_id == "POL-007" for v in result.hard_violations)

    def test_unapproved_category_violates_pol005(self) -> None:
        # Bypass the IntakeClaim Literal validation — emulate a model that
        # produced an unexpected category string.
        claim = _claim()
        claim.category = "shopping"  # type: ignore[assignment]
        result = evaluate_hard_rules(claim, receipt_text="Vendor receipt — total MYR 250.00")
        assert any(v.rule_id == "POL-005" for v in result.hard_violations)

    def test_other_category_is_soft_flag_not_block(self) -> None:
        result = evaluate_hard_rules(_claim(category="other"), receipt_text="Vendor receipt — total MYR 250.00")
        assert not any(v.rule_id == "POL-005" for v in result.hard_violations)
        assert any("uncategorized_expense" in f for f in result.ambiguous_flags)


class TestAmbiguousFlags:
    def test_low_confidence_emits_flag(self) -> None:
        result = evaluate_hard_rules(_claim(confidence=0.3), receipt_text="Vendor receipt — total MYR 250.00")
        assert any("low_intake_confidence" in f for f in result.ambiguous_flags)

    def test_monthly_billing_above_threshold_emits_annual_hint(self) -> None:
        result = evaluate_hard_rules(
            _claim(amount_myr=300, billing_period="monthly"),
            receipt_text="Vendor receipt — total MYR 250.00",
        )
        assert any("annual_plan_preferred" in f for f in result.ambiguous_flags)


class TestFastReject:
    def test_fast_reject_when_block_violation_present(self) -> None:
        result = evaluate_hard_rules(
            _claim(business_justification="x"),  # POL-004 block
            receipt_text="Vendor receipt — total MYR 250.00",
        )
        assert result.fast_reject is True

    def test_no_fast_reject_when_only_soft_flags(self) -> None:
        result = evaluate_hard_rules(_claim(confidence=0.4), receipt_text="Vendor receipt — total MYR 250.00")
        assert result.fast_reject is False
