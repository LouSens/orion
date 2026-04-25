"""FastAPI entrypoint + minimal demo UI.

Endpoints:
  GET  /                           — single-page HTML demo
  GET  /api/health                 — status: model, langsmith live, project
  POST /api/submit                 — run the full workflow; returns state + trace URL
  POST /api/parse-document         — extract text from PDF/DOCX/TXT upload
  GET  /api/ledger                 — recent decisions
  GET  /api/audit/export           — CSV export with optional filters (P4.1)
  GET  /api/audit/report           — markdown summary with stats (P4.1)
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import traceback
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from langsmith import Client as LangSmithClient
from langsmith.run_helpers import get_current_run_tree, traceable

from .config import langsmith_is_live, settings, wire_langsmith
from .graph import workflow
from .schemas import ReimbursementSubmission
from .state import WorkflowState
from .tools import (
    DocumentTooLargeError,
    Ledger,
    UnsupportedDocumentError,
    parse_document,
)

wire_langsmith()

app = FastAPI(title="Orion Reimburse", version="0.2.0")
_ledger = Ledger()
_index_html = (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")
_ls_client: LangSmithClient | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ls() -> LangSmithClient | None:
    global _ls_client
    if not langsmith_is_live():
        return None
    if _ls_client is None:
        _ls_client = LangSmithClient()
    return _ls_client


def _submission_hash(sub: ReimbursementSubmission) -> str:
    """SHA256 of all submission fields (sorted keys) — no timestamp in submission.
    Used as idempotency key to detect duplicate POSTs (P1.6).
    """
    data = sub.model_dump(mode="json")
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _filter_records(
    records: list[dict],
    employee_id: Optional[str],
    decision: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
) -> list[dict]:
    """Apply optional filters to a list of ledger records."""
    out = records
    if employee_id:
        out = [r for r in out if r.get("employee_id") == employee_id]
    if decision:
        out = [r for r in out if r.get("decision") == decision]
    if from_date:
        out = [r for r in out if r.get("recorded_at", "") >= from_date]
    if to_date:
        out = [r for r in out if r.get("recorded_at", "") <= to_date + "Z"]
    return out


@traceable(run_type="chain", name="orion.workflow")
def _run_workflow(initial: WorkflowState) -> tuple[WorkflowState, str | None]:
    """Wrap the graph invocation in a root-level trace so every agent
    shows up under a single run id. Returns (final_state, run_id)."""
    rt = get_current_run_tree()
    run_id = str(rt.id) if rt is not None else None
    final = workflow.invoke(initial)
    return final, run_id


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _index_html


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "model": settings.ilmu_model,
        "langsmith": langsmith_is_live(),
        "langsmith_project": settings.langsmith_project,
        "langsmith_dashboard": settings.langsmith_dashboard_url,
    }


@app.post("/api/submit")
def submit(payload: ReimbursementSubmission) -> JSONResponse:
    # P1.6 — Idempotency gate: compute submission hash, return cached result on duplicate hit
    sub_hash = _submission_hash(payload)
    for r in _ledger.all():
        if r.get("submission_hash") == sub_hash:
            return JSONResponse({
                "cached": True,
                "original_claim_id": r.get("claim_id"),
                "decision": r.get("decision"),
                "recorded_at": r.get("recorded_at"),
                "message": "Duplicate submission detected — returning cached result. No LLM calls were made.",
            })

    claim_id = f"CLM-{uuid.uuid4().hex[:8].upper()}"
    initial: WorkflowState = {
        "claim_id": claim_id,
        "submission": payload,
        "submission_hash": sub_hash,  # P1.6: recorder will persist this
        "trace": [],
        "retry_count": 0,
        "supervisor_visits": 0,
        "terminal": False,
        "error": None,
    }
    try:
        final, run_id = _run_workflow(initial)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(500, f"Workflow failure: {e}") from e

    body = _serialize(final)
    body["langsmith"] = _langsmith_refs(run_id)
    return JSONResponse(body)


@app.post("/api/parse-document")
async def parse_upload(file: UploadFile = File(...)) -> JSONResponse:
    """Parse a PDF/DOCX/TXT and return its extracted text.
    The UI pipes the returned text into the receipt_text textarea so the
    Intake agent can read it verbatim."""
    data = await file.read()
    try:
        parsed = parse_document(
            file.filename or "upload.bin",
            data,
            max_bytes=settings.max_upload_bytes,
        )
    except UnsupportedDocumentError as e:
        raise HTTPException(415, str(e)) from e
    except DocumentTooLargeError as e:
        raise HTTPException(413, str(e)) from e
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(400, f"Failed to parse document: {e}") from e

    return JSONResponse(parsed.to_dict())


@app.get("/api/ledger")
def ledger() -> dict:
    return {"records": _ledger.all()}


@app.get("/api/audit/export")
def audit_export(
    employee_id: Optional[str] = Query(None, description="Filter by employee ID (e.g. E003)"),
    decision: Optional[str] = Query(None, description="Filter by decision value (e.g. auto_reject)"),
    from_date: Optional[str] = Query(None, description="ISO date lower bound (e.g. 2026-01-01)"),
    to_date: Optional[str] = Query(None, description="ISO date upper bound (e.g. 2026-04-30)"),
) -> Response:
    """Export filtered ledger records as a CSV file (P4.1)."""
    records = _filter_records(_ledger.all(), employee_id, decision, from_date, to_date)
    fields = [
        "claim_id", "employee_id", "vendor", "product",
        "amount_myr", "decision", "recorded_at", "submission_hash",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in records:
        writer.writerow({f: r.get(f, "") for f in fields})
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orion_audit_export.csv"},
    )


@app.get("/api/audit/report")
def audit_report(
    employee_id: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
) -> Response:
    """Return a markdown audit summary with decision stats (P4.1)."""
    all_records = _ledger.all()
    records = _filter_records(all_records, employee_id, decision, from_date, to_date)

    total = len(records)
    total_amount = sum(r.get("amount_myr", 0.0) for r in records)
    by_decision: dict[str, int] = {}
    for r in records:
        d = r.get("decision", "unknown")
        by_decision[d] = by_decision.get(d, 0) + 1

    decision_rows = "\n".join(
        f"| {d} | {count} | {count / total * 100:.1f}% |"
        for d, count in sorted(by_decision.items(), key=lambda x: -x[1])
    ) if total else "| — | 0 | — |"

    filter_desc = " — ".join(filter(None, [
        f"employee: `{employee_id}`" if employee_id else None,
        f"decision: `{decision}`" if decision else None,
        f"from: `{from_date}`" if from_date else None,
        f"to: `{to_date}`" if to_date else None,
    ])) or "no filters applied"

    recent_rows = "\n".join(
        f"| {r.get('claim_id','')} | {r.get('employee_id','')} | {r.get('vendor','')} "
        f"| MYR {r.get('amount_myr', 0):.2f} | {r.get('decision','')} | {r.get('recorded_at','')[:10]} |"
        for r in records[-10:]
    ) or "| — | — | — | — | — | — |"

    md = f"""# Orion Audit Report

**Generated:** {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
**Filters:** {filter_desc}

## Summary

| Metric | Value |
|---|---|
| Total claims in scope | {total} |
| Total of all records | {len(all_records)} |
| Total amount (MYR) | {total_amount:,.2f} |

## Decisions Breakdown

| Decision | Count | Share |
|---|---|---|
{decision_rows}

## Most Recent 10 Claims

| Claim ID | Employee | Vendor | Amount | Decision | Date |
|---|---|---|---|---|---|
{recent_rows}

---
*Export this report as CSV via `GET /api/audit/export` with the same query parameters.*
"""
    return Response(content=md, media_type="text/markdown")

def _serialize(state: WorkflowState) -> dict:
    def _dump(v: Any) -> Any:
        if v is None:
            return None
        if hasattr(v, "model_dump"):
            return v.model_dump(mode="json")
        return v

    return {
        "claim_id": state.get("claim_id"),
        "trace": state.get("trace", []),
        "terminal": state.get("terminal", False),
        "intake": _dump(state.get("intake")),
        "intelligence": _dump(state.get("intelligence")),
        "policy": _dump(state.get("policy")),
        "approval": _dump(state.get("approval")),
        "record": _dump(state.get("record")),
    }


def _langsmith_refs(run_id: str | None) -> dict:
    """Return the info the UI needs to render a deep-link to LangSmith."""
    info = {
        "enabled": langsmith_is_live(),
        "project": settings.langsmith_project,
        "run_id": run_id,
        "project_url": f"{settings.langsmith_dashboard_url.rstrip('/')}/",
        "run_url": None,
    }
    client = _ls()
    if client is not None and run_id:
        try:
            run = client.read_run(run_id)
            # Prefer the SDK-provided URL (private, includes org slug).
            info["run_url"] = getattr(run, "url", None)
        except Exception:  # noqa: BLE001
            # Read may race with trace flush; a null run_url is fine.
            info["run_url"] = None
    return info


def run() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=False)


if __name__ == "__main__":
    run()
