"""Unit tests for the policy JSON loader.

Requirement: R3 — policy rule metadata feeds the policy engine + Supervisor.
Module under test: app/tools/policy_store.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.policy_store import PolicyStore


@pytest.fixture
def custom_store(tmp_path: Path) -> PolicyStore:
    payload = {
        "hard_policies": [
            {
                "rule_id": "POL-X",
                "title": "Test hard rule",
                "description": "Always blocks.",
                "enforcement": "automatic",
            },
            {
                "rule_id": "POL-Y",
                "title": "LLM-evaluated rule",
                "description": "Routed via LLM.",
                "enforcement": "llm_evaluated",
            },
        ],
        "soft_policies": [
            {
                "rule_id": "POL-Z",
                "title": "Test soft rule",
                "description": "Hint only.",
                "enforcement": "automatic",
            },
        ],
    }
    f = tmp_path / "policies.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    return PolicyStore(path=f)


def test_severity_for_hard_rule(custom_store: PolicyStore) -> None:
    assert custom_store.severity_for("POL-X") == "block"


def test_severity_for_soft_rule(custom_store: PolicyStore) -> None:
    assert custom_store.severity_for("POL-Z") == "warn"


def test_severity_for_unknown_rule_defaults_to_warn(custom_store: PolicyStore) -> None:
    assert custom_store.severity_for("POL-NOPE") == "warn"


def test_automatic_rule_ids_excludes_llm_evaluated(custom_store: PolicyStore) -> None:
    ids = custom_store.automatic_rule_ids()
    assert "POL-X" in ids
    assert "POL-Z" in ids
    assert "POL-Y" not in ids  # llm_evaluated is filtered out


def test_by_rule_id_returns_full_rule(custom_store: PolicyStore) -> None:
    rule = custom_store.by_rule_id("POL-X")
    assert rule is not None
    assert rule["title"] == "Test hard rule"


def test_by_rule_id_returns_none_for_missing(custom_store: PolicyStore) -> None:
    assert custom_store.by_rule_id("POL-NOPE") is None


def test_as_prompt_block_lists_both_sections(custom_store: PolicyStore) -> None:
    block = custom_store.as_prompt_block()
    assert "Hard rules" in block
    assert "Soft rules" in block
    assert "POL-X" in block
    assert "POL-Z" in block
