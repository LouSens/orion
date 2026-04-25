"""Live ILMU + LangSmith regression tests. SKIPPED unless `--runlive` is passed.

Requirement: R7 — verifies the production LLM path actually works end-to-end.
Used in the nightly CI workflow and for manual local validation.

Credentials resolution: the gate reads `settings.ilmu_api_key` /
`settings.langsmith_api_key`, which pydantic-settings hydrates from `.env`.
A bare `os.getenv` would miss the local `.env` case (pydantic-settings does
not push values into the process environment).
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import langsmith_is_live, settings, wire_langsmith
from tests.fixtures.payloads import PAYLOADS

EXPECTED_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "expected.yaml"

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def expected() -> dict:
    return yaml.safe_load(EXPECTED_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def real_client(tmp_data_dir: Path) -> TestClient:  # noqa: ARG001
    if not settings.ilmu_api_key or settings.ilmu_api_key in ("dev-key", "replace-me"):
        pytest.skip("ILMU_API_KEY not set in env or .env — cannot run live test")
    # `wire_langsmith()` will export tracing env vars from settings if a real
    # LangSmith key is present; otherwise live runs proceed without tracing.
    wire_langsmith()
    from app.main import app
    return TestClient(app)


@pytest.mark.parametrize("scenario_name", list(PAYLOADS.keys()))
def test_live_scenario_within_band_and_sla(
    scenario_name: str, real_client: TestClient, expected: dict,
) -> None:
    payload = PAYLOADS[scenario_name].model_dump(mode="json")
    t0 = time.time()
    r = real_client.post("/api/submit", json=payload)
    elapsed = time.time() - t0

    assert r.status_code == 200, r.text
    assert elapsed < 120, f"{scenario_name}: SLA breach — {elapsed:.1f}s > 120s"

    body = r.json()
    decision = body["approval"]["decision"]
    band = expected[scenario_name]["decision_band"]
    assert decision in band, (
        f"{scenario_name}: live decision {decision!r} not in band {band}"
    )

    # LangSmith deep-link sanity: present iff tracing is enabled for the run.
    ls = body["langsmith"]
    if langsmith_is_live():
        assert ls["enabled"] is True
        assert ls["run_id"], "tracing enabled but no run_id surfaced"
