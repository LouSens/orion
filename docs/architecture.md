# Orion Architecture — Current Implementation

Orion is an API-first backend that orchestrates LLM agents for subscription
reimbursement approval. All agents are connected via a LangGraph state graph.

## System Components

### 1. API Layer — `app/main.py` (FastAPI)

- Accepts `POST /api/submit` with a JSON `ReimbursementSubmission` body.
- Idempotency gate: SHA-256 hashes each submission; duplicate POSTs return the
  cached result without re-running the workflow.
- Invokes the LangGraph `workflow` and returns the final `WorkflowState` plus
  LangSmith trace URLs.
- Exposes `GET /api/health`, `GET /api/ledger`, `GET /api/audit/export` (CSV),
  and `GET /api/audit/report` (Markdown summary).
- Hosts a minimal HTML frontend at `app/web/index.html`.

### 2. Orchestration Layer — `app/graph.py` (LangGraph)

Core logic as a directed state graph. **Non-linear** — parallel branches for
Intelligence and Policy, a fast-reject short-circuit, and a Supervisor that
dynamically routes across five paths.

```
START → intake → [intelligence ∥ policy_check] → merge_intel_policy
                                                        │
                                              _fast_reject_route
                                             /                   \
                                (fast_reject=True)          (normal path)
                                            │                     │
                                          critic              supervisor
                                                           /    |    |    \     \
                               route_to_approval──────► critic  │    │     │     │
                               route_back_to_intel ─────────► intelligence │     │
                               route_back_to_policy ──────────────► policy_check │
                               request_human_escalation ────────────────► escalate_node
                               request_user_clarification ─────────────────────► clarify_node
                                                                  │
                                    critic, escalate_node, clarify_node → recorder → END
```

**Loop protection:** `supervisor_visits` is incremented each time the Supervisor
runs. At `supervisor_visits >= 3` the LLM call is skipped and the graph forces
`request_human_escalation` to prevent infinite loops.

**State object:** `WorkflowState` (`app/state.py`) — a `TypedDict` passed
node-to-node, accumulating outputs: `intake`, `intelligence`, `policy`,
`supervisor`, `approval`, `record`.

### 3. Agent Layer — `app/agents/` (LangChain + GLM-5.1 via ILMU)

All LLM agents call `chat_structured()` from `app/llm.py`, which:
- Injects the Pydantic output schema into the system prompt.
- Retries once on parse/validation failure (error fed back to the model).
- Falls back from JSON-mode to schema-injection-only if the server rejects it.
- Wraps each call with `@traceable` for LangSmith observability.

The Intelligence Agent uniquely runs a **tool-calling loop** (up to 5
iterations) where the LLM drives its own investigation.

### 4. Tooling Layer — `app/tools/`

| File | Purpose |
|---|---|
| `amount_extractor.py` | Regex-based currency extractor; anti-hallucination pre-pass for Intake |
| `document_parser.py` | Converts uploaded PDF/DOCX/TXT to raw text (pypdf, python-docx) |
| `ledger.py` | JSON-file ledger — read/write of `LedgerRecord` entries |
| `ledger_search.py` | 4 LangChain `@tool` functions for Intelligence; returns pre-computed signals |
| `policy_engine.py` | Deterministic Python hard-rule evaluator (no LLM) |
| `policy_store.py` | Loads `data/policies.json` — retained for compatibility, not used in main graph |
| `subscription_catalog.py` | Loads `data/org_subscriptions.json`, fuzzy pre-filter via rapidfuzz |

### 5. Observability — LangSmith

Every agent node and LLM call is decorated with `@traceable`. When
`LANGSMITH_TRACING=true` and a valid `LANGSMITH_API_KEY` are set, every
workflow run produces a full trace tree showing inputs, outputs, latency,
and token usage for each agent and tool call.

---

## Data Layer

```
data/
├── ledger.json             # Persisted LedgerRecord entries (append-only, 80+ seed records)
├── org_subscriptions.json  # Active org-wide SaaS licences + approved catalog (30+ entries)
└── policies.json           # Corporate reimbursement rules (POL-001–POL-008)
```

---

## Project Layout

```
orion/
├── app/
│   ├── main.py             # FastAPI application entry point
│   ├── graph.py            # LangGraph workflow (nodes + edges)
│   ├── state.py            # WorkflowState TypedDict
│   ├── schemas.py          # Pydantic I/O models for all agents
│   ├── config.py           # Settings (env vars, per-agent LLM config)
│   ├── llm.py              # ILMU/GLM-5.1 client wrapper + chat_structured
│   ├── agents/
│   │   ├── intake.py       # Extracts structured claim; regex currency pre-pass
│   │   ├── intelligence.py # Tool-calling loop: duplicate + fraud investigation
│   │   ├── supervisor.py   # LLM-driven dynamic router (5 paths)
│   │   ├── critic.py       # Adversarial final reviewer (tries to reject first)
│   │   └── recorder.py     # Persists outcome to ledger (no LLM)
│   ├── tools/
│   │   ├── amount_extractor.py   # Regex currency extraction + discrepancy flag
│   │   ├── document_parser.py
│   │   ├── ledger.py
│   │   ├── ledger_search.py      # Pre-computed anomaly/duplicate/vendor signals
│   │   ├── policy_engine.py      # Deterministic hard-rule evaluator
│   │   ├── policy_store.py       # (retained, not used in main graph)
│   │   └── subscription_catalog.py
│   └── web/
│       └── index.html      # Minimal demo UI (served by FastAPI)
├── data/                   # JSON data files (ledger, catalog, policies)
├── docs/                   # This directory — code-state documentation
├── plan/                   # Design intent documents (v2 plan — now implemented)
├── scripts/
│   └── smoke.py            # End-to-end smoke test (5 canned scenarios)
├── requirements.txt
└── README.md
```

## Key Dependencies

| Package | Role |
|---|---|
| `langgraph >= 1.0.2` | State graph orchestration |
| `langchain-core >= 1.1.0` | `@tool` decorator for Intelligence tools |
| `langsmith >= 0.1.140` | Tracing + observability |
| `openai >= 1.40.0` | OpenAI-compatible client for ILMU/GLM-5.1 |
| `pydantic >= 2.8.0` | Structured agent I/O schemas |
| `fastapi >= 0.115.0` | API layer |
| `rapidfuzz >= 3.9.0` | Fuzzy pre-filter in SubscriptionCatalog and ledger_search |
| `pypdf >= 5.0.0` | PDF parsing |
| `python-docx >= 1.1.2` | DOCX parsing |
