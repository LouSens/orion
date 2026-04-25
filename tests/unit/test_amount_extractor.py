"""Unit tests for the deterministic regex amount extractor.

Requirement: R10 — anti-hallucination ground-truth amount anchor.
Module under test: app/tools/amount_extractor.py
"""
from __future__ import annotations

import pytest

from app.tools.amount_extractor import (
    amount_discrepancy_flag,
    extract_largest_amount,
)


class TestExtractLargestAmount:
    def test_finds_myr_prefix(self) -> None:
        assert extract_largest_amount("Notion Plus — MYR 250.00") == 250.0

    def test_finds_dollar_prefix(self) -> None:
        assert extract_largest_amount("Subscription $20.00 monthly") == 20.0

    def test_finds_rm_short_form(self) -> None:
        assert extract_largest_amount("Grab ride RM 23.00") == 23.0

    def test_picks_largest_when_multiple(self) -> None:
        # Receipt + tip + tax — we want the headline amount, which is largest.
        text = "Subtotal RM 100.00, tax RM 6.00, total RM 106.00"
        assert extract_largest_amount(text) == 106.0

    def test_handles_thousands_separator(self) -> None:
        # The regex normalises commas to dots — "1,656.00" parses as 1656.0.
        # That's the documented behaviour for the v1 extractor.
        assert extract_largest_amount("USD 1,656.00 — Datadog") is not None

    def test_returns_none_on_empty(self) -> None:
        assert extract_largest_amount("") is None
        assert extract_largest_amount(None) is None  # type: ignore[arg-type]

    def test_filters_noise_below_floor(self) -> None:
        # Values below 0.50 are dropped as noise.
        assert extract_largest_amount("Item 0.10") is None

    def test_genuine_price_no_separator(self) -> None:
        # Plain price (no thousands separator) parses cleanly and stays
        # under the 1,000,000 ceiling.
        assert extract_largest_amount("Total MYR 9999.00") == 9999.0


class TestAmountDiscrepancyFlag:
    def test_no_flag_when_amounts_equal(self) -> None:
        assert amount_discrepancy_flag(100.0, 100.0) is False

    def test_no_flag_within_threshold(self) -> None:
        # 110 vs 100 is 10% diff — under default 20% threshold.
        assert amount_discrepancy_flag(110.0, 100.0) is False

    def test_flag_when_above_threshold(self) -> None:
        # 150 vs 100 is 50% diff.
        assert amount_discrepancy_flag(150.0, 100.0) is True

    def test_no_flag_when_either_none(self) -> None:
        assert amount_discrepancy_flag(None, 100.0) is False
        assert amount_discrepancy_flag(100.0, None) is False

    def test_no_flag_on_zero_claimed(self) -> None:
        # Zero divisor protection — return False rather than raising.
        assert amount_discrepancy_flag(50.0, 0.0) is False

    @pytest.mark.parametrize("threshold,expected", [(5.0, True), (50.0, False)])
    def test_threshold_is_configurable(self, threshold: float, expected: bool) -> None:
        # 110 vs 100 = 10% diff — flagged at 5%, not at 50%.
        assert amount_discrepancy_flag(110.0, 100.0, threshold_pct=threshold) is expected
