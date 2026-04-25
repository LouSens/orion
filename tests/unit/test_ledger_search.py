"""Unit tests for the four Intelligence-agent investigation tools.

Requirement: R4 — duplicate detection + cross-referencing rely on these tools.
Module under test: app/tools/ledger_search.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.tools.ledger_search import (
    lookup_subscription_catalog,
    search_employee_history,
    search_ledger_by_amount,
    search_ledger_by_merchant,
)


@pytest.fixture
def seeded_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a tiny ledger + catalog in tmp and rewire `settings.data_dir`."""
    now = datetime.now(timezone.utc)
    ledger_records = [
        {
            "claim_id": "C-1", "employee_id": "E-1",
            "vendor": "Notion Labs Inc.", "product": "Notion Plus",
            "amount_myr": 250.0, "decision": "auto_reject",
            "recorded_at": (now - timedelta(days=10)).isoformat(),
        },
        {
            "claim_id": "C-2", "employee_id": "E-1",
            "vendor": "Notion Labs Inc.", "product": "Notion Plus",
            "amount_myr": 250.0, "decision": "auto_reject",
            "recorded_at": (now - timedelta(days=40)).isoformat(),
        },
        {
            "claim_id": "C-3", "employee_id": "E-2",
            "vendor": "OpenAI", "product": "ChatGPT Plus",
            "amount_myr": 96.0, "decision": "escalate_manager",
            "recorded_at": (now - timedelta(days=5)).isoformat(),
        },
    ]
    catalog = {
        "active_licenses": [
            {
                "id": "ORG-SUB-001", "vendor": "Notion Labs Inc.",
                "product": "Notion Team Plan", "category": "productivity",
                "seats_total": 50, "seats_used": 41, "seats_available": 9,
                "owner_team": "Operations", "renewal_date": "2026-11-30",
                "aliases": ["Notion", "Notion Plus"],
            },
        ],
        "approved_catalog": [
            {"product": "Claude Pro", "vendor": "Anthropic",
             "category": "ai_tools", "note": "Approved for individual claims."},
        ],
    }
    (tmp_path / "ledger.json").write_text(
        json.dumps({"records": ledger_records}), encoding="utf-8",
    )
    (tmp_path / "org_subscriptions.json").write_text(
        json.dumps(catalog), encoding="utf-8",
    )

    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


class TestSearchByAmount:
    def test_finds_within_tolerance(self, seeded_data_dir: Path) -> None:
        out = json.loads(search_ledger_by_amount.invoke(
            {"amount": 250.0, "tolerance_pct": 5.0, "employee_id": "E-1"}
        ))
        assert out["count"] == 2

    def test_signals_exact_dup_count(self, seeded_data_dir: Path) -> None:
        out = json.loads(search_ledger_by_amount.invoke(
            {"amount": 250.0, "tolerance_pct": 5.0, "employee_id": "E-1"}
        ))
        assert out["duplicate_signals"]["exact_duplicate_count"] >= 2
        assert out["duplicate_signals"]["same_employee_matches"] == 2

    def test_zero_amount_returns_empty(self, seeded_data_dir: Path) -> None:
        out = json.loads(search_ledger_by_amount.invoke({"amount": 0}))
        assert out["matches"] == []


class TestSearchByMerchant:
    def test_substring_match_for_notion(self, seeded_data_dir: Path) -> None:
        out = json.loads(search_ledger_by_merchant.invoke(
            {"merchant_name": "notion", "employee_id": "E-1"}
        ))
        assert out["count"] == 2
        assert out["vendor_signals"]["employee_claim_count"] == 2

    def test_empty_merchant_returns_empty(self, seeded_data_dir: Path) -> None:
        out = json.loads(search_ledger_by_merchant.invoke({"merchant_name": ""}))
        assert out["matches"] == []


class TestSearchEmployeeHistory:
    def test_filters_by_window(self, seeded_data_dir: Path) -> None:
        out = json.loads(search_employee_history.invoke(
            {"employee_id": "E-1", "days_back": 30}
        ))
        # Only the claim from 10 days ago is in-window.
        assert out["total_in_window"] == 1
        assert out["all_time_total"] == 2

    def test_unknown_employee_returns_zero(self, seeded_data_dir: Path) -> None:
        out = json.loads(search_employee_history.invoke(
            {"employee_id": "E-NOPE", "days_back": 90}
        ))
        assert out["all_time_total"] == 0


class TestLookupCatalog:
    def test_finds_active_license_via_alias(self, seeded_data_dir: Path) -> None:
        out = json.loads(lookup_subscription_catalog.invoke({"merchant_name": "Notion Plus"}))
        assert out["found_active"] is True
        assert out["active_licenses"][0]["id"] == "ORG-SUB-001"

    def test_finds_approved_catalog(self, seeded_data_dir: Path) -> None:
        out = json.loads(lookup_subscription_catalog.invoke({"merchant_name": "Claude Pro"}))
        assert out["found_in_catalog"] is True

    def test_no_match_returns_both_empty(self, seeded_data_dir: Path) -> None:
        out = json.loads(lookup_subscription_catalog.invoke({"merchant_name": "Tableau"}))
        assert out["found_active"] is False
        assert out["found_in_catalog"] is False
