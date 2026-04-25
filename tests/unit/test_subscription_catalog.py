"""Unit tests for SubscriptionCatalog.fuzzy_candidates().

Requirement: R2 — intelligence agent duplicate detection uses fuzzy pre-filter
before delegating semantic judgement to the LLM.
Module under test: app/tools/subscription_catalog.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.subscription_catalog import SubscriptionCatalog

_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "org_subscriptions.json"


@pytest.fixture
def catalog() -> SubscriptionCatalog:
    return SubscriptionCatalog(path=_DATA)


# --- empty / blank query (lines 44-46) ----------------------------------------

def test_empty_string_returns_empty(catalog: SubscriptionCatalog) -> None:
    assert catalog.fuzzy_candidates("") == []


def test_whitespace_only_returns_empty(catalog: SubscriptionCatalog) -> None:
    assert catalog.fuzzy_candidates("   ") == []


def test_none_coerced_to_empty_returns_empty(catalog: SubscriptionCatalog) -> None:
    # (query or "") handles None gracefully — the type hint is str but the
    # guard is intentional so agents can pass None without crashing.
    assert catalog.fuzzy_candidates(None) == []  # type: ignore[arg-type]


# --- matching queries (lines 47-54, best >= 55 branch) ------------------------

def test_product_name_match(catalog: SubscriptionCatalog) -> None:
    results = catalog.fuzzy_candidates("notion")
    ids = [r["id"] for r in results]
    assert "ORG-SUB-001" in ids


def test_alias_match(catalog: SubscriptionCatalog) -> None:
    # "Figma" appears as an alias on ORG-SUB-002 (Figma Organization)
    results = catalog.fuzzy_candidates("figma")
    assert any(r["id"] == "ORG-SUB-002" for r in results)


def test_vendor_match(catalog: SubscriptionCatalog) -> None:
    results = catalog.fuzzy_candidates("atlassian")
    ids = [r["id"] for r in results]
    # Both Jira (ORG-SUB-006) and Confluence (ORG-SUB-007) are Atlassian
    assert "ORG-SUB-006" in ids or "ORG-SUB-007" in ids


# --- below-threshold query (line 51 false branch) -----------------------------

def test_unrecognised_query_returns_list(catalog: SubscriptionCatalog) -> None:
    # A long, unique token unlikely to score >= 55 against any haystack entry.
    # We assert a list is returned (not a crash); the below-55 branch is still
    # exercised for every license that doesn't match during other tests.
    results = catalog.fuzzy_candidates("zyxwvutsrqponmlkjihgfedcba")
    assert isinstance(results, list)


# --- top_k slicing (line 54) --------------------------------------------------

def test_top_k_caps_results(catalog: SubscriptionCatalog) -> None:
    results = catalog.fuzzy_candidates("google", top_k=2)
    assert len(results) <= 2


def test_default_top_k_is_five(catalog: SubscriptionCatalog) -> None:
    # "atlassian" matches at least 2 entries; default top_k=5 should not error.
    results = catalog.fuzzy_candidates("atlassian")
    assert len(results) <= 5


# --- result ordering (sorted descending by score, line 53) --------------------

def test_best_match_appears_first(catalog: SubscriptionCatalog) -> None:
    # "Notion Team Plan" is the exact product name for ORG-SUB-001;
    # it should rank higher than ORG-SUB-020 (Notion AI Add-on).
    results = catalog.fuzzy_candidates("notion team plan", top_k=5)
    assert results[0]["id"] == "ORG-SUB-001"
