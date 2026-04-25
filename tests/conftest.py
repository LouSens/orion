"""Shared pytest fixtures for the Orion test suite.

Three responsibilities:

1. **Isolation** — point the JSON ledger and LangSmith export at temp dirs so
   tests never write to `data/ledger.json` or hit a real tracing endpoint.
2. **Stub LLM** — install a deterministic fake for `chat_structured` and `chat`
   so unit + stub-integration tests run offline. The fake mirrors the canned
   logic in `scripts/smoke.py` but is centralised here.
3. **--runlive flag** — opt-in marker for live ILMU calls. By default `live`
   tests are skipped so PR CI stays green without secrets.

NOTE on import order: pytest imports test modules (which transitively import
`app.config`, instantiating the `Settings` pydantic model) BEFORE any fixture
body runs. If `.env` contains real `LANGSMITH_TRACING=true`, by the time a
fixture could "disable tracing" the Settings object already has it on. So the
disable below runs at conftest module-level — environment variables that
pydantic-settings reads MUST be set before the first `app.*` import.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module-level: force LangSmith tracing OFF for the whole offline test run.
# Skipped when `--runlive` is on the command line, so live tests can still
# emit real traces through the user's API key from `.env`.
# ---------------------------------------------------------------------------
if "--runlive" not in sys.argv:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    # `Settings.langsmith_tracing` reads from os.environ first, then .env;
    # the explicit "false" above wins over any value in the user's .env.


# ---------------------------------------------------------------------------
# CLI options & marker filtering
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--runlive",
        action="store_true",
        default=False,
        help="run @pytest.mark.live tests (hits real ILMU + LangSmith APIs)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--runlive"):
        return
    skip_live = pytest.mark.skip(reason="needs --runlive (real API key required)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


# ---------------------------------------------------------------------------
# Environment isolation — per-test sandboxes
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect `settings.data_dir` to a fresh tmp dir and seed it with copies
    of the production data files. Tests can mutate freely without touching
    the repo's `data/` directory.

    Also rebinds the `path` attribute on every module-level `_ledger`
    instance — those are constructed at import time, so a plain
    `settings.data_dir` patch arrives too late to retarget them.
    """
    src = Path(__file__).resolve().parent.parent / "data"
    for fname in ("policies.json", "org_subscriptions.json"):
        (tmp_path / fname).write_text(
            (src / fname).read_text(encoding="utf-8"), encoding="utf-8"
        )
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps({"records": []}), encoding="utf-8")

    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    # Retarget any already-instantiated Ledger singletons.
    for module_path in ("app.main", "app.agents.recorder"):
        try:
            mod = __import__(module_path, fromlist=["_ledger", "ledger"])
        except ImportError:
            continue
        ledger_inst = getattr(mod, "_ledger", getattr(mod, "ledger", None))
        if ledger_inst is not None:
            monkeypatch.setattr(ledger_inst, "path", ledger_path)

    return tmp_path


# ---------------------------------------------------------------------------
# Stub LLM — canned outputs keyed off prompt content
# ---------------------------------------------------------------------------

def _build_fake_chat_structured():
    """Factory that produces the canned-LLM callable. Lifted from
    `scripts/smoke.py` so the test suite and the offline smoke share one
    source of truth for what each scenario should look like."""
    import re

    def _fake(messages, schema, *, temperature=0.1, max_retries=1, cfg=None, **_kw):
        full_text = " ".join(m.get("content", "") for m in messages if isinstance(m, dict))
        user_text = " ".join(
            m.get("content", "") for m in messages
            if isinstance(m, dict) and m.get("role") != "system"
        )
        full_low = user_text.lower()
        claim_section_m = re.search(
            r"extracted claim:(.*?)(?:\n\n|\Z)", full_text, re.IGNORECASE | re.DOTALL,
        )
        claim_section = (claim_section_m.group(1) if claim_section_m else full_text).lower()
        name = schema.__name__
        low = claim_section

        if name == "IntakeClaim":
            if "datadog" in low:
                return schema.model_validate(dict(
                    vendor="Datadog Inc.", product="Datadog Pro",
                    category="engineering", amount_myr=7800.0, currency_original="USD",
                    amount_original=1656.0, billing_period="annual",
                    purchase_date="2026-04-20",
                    business_justification="Payments service observability",
                    confidence=0.9, missing_fields=[],
                ))
            if "notion" in low:
                return schema.model_validate(dict(
                    vendor="Notion Labs Inc.", product="Notion Plus",
                    category="productivity", amount_myr=250.0, currency_original="MYR",
                    amount_original=250.0, billing_period="monthly",
                    purchase_date="2026-04-25",
                    business_justification="Team SOPs and documentation",
                    confidence=0.9, missing_fields=[],
                ))
            if "chatgpt" in low or "openai" in low:
                return schema.model_validate(dict(
                    vendor="OpenAI", product="ChatGPT Plus",
                    category="ai_tools", amount_myr=96.0, currency_original="USD",
                    amount_original=20.0, billing_period="monthly",
                    purchase_date="2026-04-15",
                    business_justification="Campaign copy and competitive research",
                    confidence=0.9, missing_fields=[],
                ))
            if "claude pro" in low:
                return schema.model_validate(dict(
                    vendor="Anthropic PBC", product="Claude Pro",
                    category="ai_tools", amount_myr=94.5, currency_original="USD",
                    amount_original=20.0, billing_period="monthly",
                    purchase_date="2026-04-10",
                    business_justification="Daily RFC drafting and code review",
                    confidence=0.92, missing_fields=[],
                ))
            return schema.model_validate(dict(
                vendor=None, product=None, category=None,
                amount_myr=200.0, billing_period="unknown",
                business_justification=None, confidence=0.25,
                missing_fields=["vendor", "product", "purchase_date", "business_justification"],
                notes="Free-text is extremely vague.",
            ))

        if name == "IntelligenceReport":
            if "notion" in low:
                return schema.model_validate(dict(
                    is_likely_duplicate=True,
                    duplicate_matches=[dict(
                        existing_subscription_id="ORG-SUB-001",
                        existing_product="Notion Team Plan", owner_team="Operations",
                        similarity_score=0.95,
                        reasoning="Same vendor, same product family; seats available.",
                    )],
                    alternatives=[dict(
                        product="Notion Team Plan (org seat)",
                        reason="9 free seats on org licence",
                        estimated_savings_myr=250.0, source="org_existing_license",
                    )],
                    cross_reference_notes="Org Notion Team Plan has 9 free seats.",
                    recommendation="block_duplicate",
                    rationale="Use existing org licence instead.",
                ))
            if "chatgpt" in low or "openai" in low:
                return schema.model_validate(dict(
                    is_likely_duplicate=True,
                    duplicate_matches=[dict(
                        existing_subscription_id="ORG-SUB-005",
                        existing_product="ChatGPT Team", owner_team="AI Platform",
                        similarity_score=0.82,
                        reasoning="Same vendor; org licence fully utilised.",
                    )],
                    alternatives=[dict(
                        product="Request expansion of ChatGPT Team",
                        reason="No seats left on org licence",
                        estimated_savings_myr=24.0, source="cheaper_tier",
                    )],
                    cross_reference_notes="ChatGPT Team is 25/25.",
                    recommendation="suggest_alternative",
                    rationale="Prefer org licence expansion.",
                ))
            if "datadog" in low:
                return schema.model_validate(dict(
                    is_likely_duplicate=False, alternatives=[],
                    cross_reference_notes="Not on approved catalog.",
                    recommendation="proceed",
                    rationale="No overlap with existing org tooling.",
                ))
            if "claude pro" in low:
                return schema.model_validate(dict(
                    is_likely_duplicate=False, alternatives=[],
                    cross_reference_notes="Within approved catalog.",
                    recommendation="proceed",
                    rationale="Approved individual claim.",
                ))
            return schema.model_validate(dict(
                is_likely_duplicate=False, alternatives=[],
                cross_reference_notes="Insufficient data.",
                recommendation="proceed",
                rationale="Defer to Supervisor.",
            ))

        if name == "SupervisorDecision":
            from app.schemas import SupervisorRoute
            intel_dup = "block_duplicate" in full_low
            intel_alt = "suggest_alternative" in full_low
            fast_rej = "fast_reject: true" in full_low
            if fast_rej or intel_dup:
                return schema.model_validate(dict(
                    route=SupervisorRoute.route_to_approval.value,
                    reasoning="Clear-cut path — route to Critic.",
                    focus_areas=[],
                ))
            if intel_alt:
                return schema.model_validate(dict(
                    route=SupervisorRoute.route_to_approval.value,
                    reasoning="Alternative suggested; manager decision.",
                    focus_areas=[],
                ))
            return schema.model_validate(dict(
                route=SupervisorRoute.route_to_approval.value,
                reasoning="No red flags. Route to Critic.",
                focus_areas=[],
            ))

        if name == "ApprovalOutcome":
            from app.schemas import ApprovalDecision
            if "7800" in full_low or "datadog" in low:
                return schema.model_validate(dict(
                    decision=ApprovalDecision.ESCALATE_FINANCE.value,
                    approver_role="finance_controller",
                    reason="Amount MYR 7800 exceeds finance threshold.",
                    confidence=0.93,
                    next_action="Route to finance controller.",
                ))
            if "block_duplicate" in full_low:
                return schema.model_validate(dict(
                    decision=ApprovalDecision.AUTO_REJECT.value,
                    approver_role=None,
                    reason="Duplicate of existing org licence; seats available.",
                    confidence=0.97,
                    next_action="Request seat on ORG-SUB-001 instead.",
                ))
            if "suggest_alternative" in full_low:
                return schema.model_validate(dict(
                    decision=ApprovalDecision.ESCALATE_MANAGER.value,
                    approver_role="direct_manager",
                    reason="Org licence preferred; expansion cheaper.",
                    confidence=0.8,
                    next_action="Manager to decide between reimbursement vs expansion.",
                ))
            return schema.model_validate(dict(
                decision=ApprovalDecision.AUTO_APPROVE.value,
                approver_role=None,
                reason="Compliant, within threshold, no duplicates.",
                confidence=0.9,
                next_action="Reimburse via next payroll cycle.",
            ))

        raise RuntimeError(f"Unhandled schema in fake LLM: {name}")

    return _fake


def _fake_chat(messages, *, temperature=0.1, max_tokens=2000, response_format_json=False):
    """Stand-in for the raw chat() used inside the Intelligence tool loop —
    immediately signal `done` so the loop exits without extra tool turns."""
    return '{"done": true}'


@pytest.fixture
def stub_llm(monkeypatch: pytest.MonkeyPatch):
    """Patch every import site of the LLM functions so all agents see the fake.

    The agents do `from ..llm import chat_structured` at module-import time,
    so monkeypatching `app.llm.chat_structured` alone is not enough — the
    binding inside each agent module must also be replaced.
    """
    from app import llm
    from app.agents import critic, intake, intelligence, supervisor

    fake = _build_fake_chat_structured()
    monkeypatch.setattr(llm, "chat_structured", fake)
    monkeypatch.setattr(llm, "chat", _fake_chat)
    for mod in (intake, intelligence, supervisor, critic):
        monkeypatch.setattr(mod, "chat_structured", fake, raising=False)
    monkeypatch.setattr(intelligence, "chat", _fake_chat, raising=False)
    return fake
