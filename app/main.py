"""FastAPI entrypoint + minimal demo UI.

Endpoints:
  GET  /                      — single-page HTML demo
  GET  /api/health            — status: model, langsmith live, project
  POST /api/submit            — run the full workflow; returns state + trace URL
  POST /api/parse-document    — extract text from PDF/DOCX/TXT upload
  GET  /api/ledger            — recent decisions
"""
from __future__ import annotations

import traceback
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
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


def _ls() -> LangSmithClient | None:
    global _ls_client
    if not langsmith_is_live():
        return None
    if _ls_client is None:
        _ls_client = LangSmithClient()
    return _ls_client


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
    claim_id = f"CLM-{uuid.uuid4().hex[:8].upper()}"
    initial: WorkflowState = {
        "claim_id": claim_id,
        "submission": payload,
        "trace": [],
        "retry_count": 0,
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
        "validation": _dump(state.get("validation")),
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
