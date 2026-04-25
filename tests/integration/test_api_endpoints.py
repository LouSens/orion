"""HTTP-layer integration tests via FastAPI's TestClient.

Requirement: R8, R9 — endpoints that the demo UI depends on. Uses the stub
LLM fixture so tests run offline.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.payloads import PAYLOADS


@pytest.fixture
def client(stub_llm, tmp_data_dir: Path) -> TestClient:  # noqa: ARG001
    """Build a fresh TestClient AFTER the stub LLM and sandboxed data dir
    are in place. Imported here (not at module top) so the env isolation in
    conftest takes effect first."""
    from app.main import app
    return TestClient(app)


def test_health_reports_model_and_tracing(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["langsmith"] is False  # forced off in test session
    assert "model" in body


def test_submit_returns_decision_and_langsmith_block(client: TestClient) -> None:
    r = client.post(
        "/api/submit",
        json=PAYLOADS["clean"].model_dump(mode="json"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["claim_id"].startswith("CLM-")
    assert body["approval"]["decision"] == "auto_approve"
    # langsmith block always present, even when disabled.
    assert "langsmith" in body
    assert body["langsmith"]["enabled"] is False


def test_submit_idempotency_returns_cached(client: TestClient) -> None:
    """Same submission twice → second hit returns the cached record without
    invoking the workflow again. Validates R6 idempotency hash."""
    payload = PAYLOADS["clean"].model_dump(mode="json")
    first = client.post("/api/submit", json=payload).json()
    second = client.post("/api/submit", json=payload).json()
    assert second.get("cached") is True
    assert second["original_claim_id"] == first["claim_id"]


def test_parse_document_text(client: TestClient) -> None:
    r = client.post(
        "/api/parse-document",
        files={"file": ("note.txt", b"Receipt: MYR 99.00", "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "txt"
    assert "MYR 99.00" in body["text"]


def test_parse_document_unsupported_415(client: TestClient) -> None:
    r = client.post(
        "/api/parse-document",
        files={"file": ("photo.jpg", b"\xff\xd8\xff", "image/jpeg")},
    )
    assert r.status_code == 415


def test_ledger_lists_after_submit(client: TestClient) -> None:
    client.post("/api/submit", json=PAYLOADS["clean"].model_dump(mode="json"))
    r = client.get("/api/ledger")
    body = r.json()
    assert isinstance(body["records"], list)
    assert len(body["records"]) >= 1


def test_audit_csv_export(client: TestClient) -> None:
    client.post("/api/submit", json=PAYLOADS["clean"].model_dump(mode="json"))
    r = client.get("/api/audit/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "claim_id" in r.text  # header row present


def test_audit_report_markdown(client: TestClient) -> None:
    client.post("/api/submit", json=PAYLOADS["clean"].model_dump(mode="json"))
    r = client.get("/api/audit/report")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "# Orion Audit Report" in r.text
