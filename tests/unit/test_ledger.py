"""Unit tests for the JSON-file ledger.

Requirement: R6 — durable record for the recorder + audit endpoints.
Module under test: app/tools/ledger.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.ledger import Ledger


@pytest.fixture
def empty_ledger(tmp_path: Path) -> Ledger:
    """A fresh Ledger pointed at a tmp file. No autoload — file does not yet exist."""
    return Ledger(path=tmp_path / "ledger.json")


def test_all_returns_empty_when_file_missing(empty_ledger: Ledger) -> None:
    assert empty_ledger.all() == []


def test_append_creates_file_and_persists(empty_ledger: Ledger) -> None:
    empty_ledger.append({"claim_id": "C-1", "employee_id": "E-1", "amount_myr": 100})
    assert empty_ledger.path.exists()
    on_disk = json.loads(empty_ledger.path.read_text(encoding="utf-8"))
    assert len(on_disk["records"]) == 1
    assert on_disk["records"][0]["claim_id"] == "C-1"


def test_append_is_additive(empty_ledger: Ledger) -> None:
    for i in range(3):
        empty_ledger.append({"claim_id": f"C-{i}", "employee_id": "E-1", "amount_myr": i})
    assert len(empty_ledger.all()) == 3


def test_by_employee_filters_correctly(empty_ledger: Ledger) -> None:
    empty_ledger.append({"claim_id": "C-1", "employee_id": "E-1"})
    empty_ledger.append({"claim_id": "C-2", "employee_id": "E-2"})
    empty_ledger.append({"claim_id": "C-3", "employee_id": "E-1"})
    by_e1 = empty_ledger.by_employee("E-1")
    assert {r["claim_id"] for r in by_e1} == {"C-1", "C-3"}


def test_concurrent_appends_serialise(empty_ledger: Ledger) -> None:
    """The lock around _read/_write should prevent torn writes when called
    from multiple threads. Smoke check, not a formal stress test."""
    import threading

    def _bulk(start: int) -> None:
        for i in range(50):
            empty_ledger.append({"claim_id": f"T-{start}-{i}", "employee_id": "E-Z"})

    threads = [threading.Thread(target=_bulk, args=(s,)) for s in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(empty_ledger.all()) == 200
