"""Full-graph integration tests using the deterministic stub LLM.

Requirement: R1, R2, R3, R4, R5, R6 — exercises the entire LangGraph workflow
against the canned-output fake LLM, asserting each scenario lands in its
expected decision band per `tests/fixtures/expected.yaml`.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.graph import build_graph
from tests.fixtures.payloads import PAYLOADS

EXPECTED_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "expected.yaml"


@pytest.fixture(scope="module")
def expected() -> dict:
    return yaml.safe_load(EXPECTED_PATH.read_text(encoding="utf-8"))


@pytest.mark.slow
@pytest.mark.parametrize("scenario_name", list(PAYLOADS.keys()))
def test_scenario_lands_in_expected_band(
    scenario_name: str,
    stub_llm,  # noqa: ARG001 — installed for side effects on agent imports
    tmp_data_dir: Path,  # noqa: ARG001 — sandboxed ledger
    expected: dict,
) -> None:
    graph = build_graph()
    payload = PAYLOADS[scenario_name]
    final = graph.invoke({
        "claim_id": f"CLM-TEST-{scenario_name.upper()}",
        "submission": payload,
        "trace": [],
        "retry_count": 0,
        "supervisor_visits": 0,
        "terminal": False,
        "error": None,
    })

    rules = expected[scenario_name]
    decision = final["approval"].decision.value

    assert decision in rules["decision_band"], (
        f"{scenario_name}: decision {decision!r} not in expected band "
        f"{rules['decision_band']}. Reason: {final['approval'].reason}"
    )
    trace_str = " ".join(final["trace"])
    for must in rules.get("trace_includes", []):
        assert must in trace_str, f"{scenario_name}: trace missing {must!r}"
    for must_not in rules.get("trace_excludes", []):
        assert must_not not in trace_str, (
            f"{scenario_name}: trace unexpectedly includes {must_not!r}"
        )


@pytest.mark.slow
def test_recorder_writes_ledger_entry(stub_llm, tmp_data_dir: Path) -> None:  # noqa: ARG001
    """Recorder must persist the decision so /api/audit endpoints have data."""
    from app.tools.ledger import Ledger

    graph = build_graph()
    final = graph.invoke({
        "claim_id": "CLM-RECORDER-TEST",
        "submission": PAYLOADS["clean"],
        "trace": [], "retry_count": 0, "supervisor_visits": 0,
        "terminal": False, "error": None,
    })
    assert final["terminal"] is True
    on_disk = Ledger().all()
    assert any(r["claim_id"] == "CLM-RECORDER-TEST" for r in on_disk)


@pytest.mark.slow
def test_terminal_state_always_has_approval(stub_llm, tmp_data_dir: Path) -> None:  # noqa: ARG001
    """Every terminating run — regardless of path — must populate `approval`
    so the recorder + UI never crash on a None field."""
    graph = build_graph()
    for name, payload in PAYLOADS.items():
        final = graph.invoke({
            "claim_id": f"CLM-TS-{name}",
            "submission": payload,
            "trace": [], "retry_count": 0, "supervisor_visits": 0,
            "terminal": False, "error": None,
        })
        assert final.get("approval") is not None, f"{name}: approval missing"
