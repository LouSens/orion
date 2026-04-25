# Orion Architecture — v2 Plan

This document describes the **target architecture** after all P1 and P2 changes are applied.
The current (v1) architecture is in `docs/architecture.md`.

---

## What Changes

| Dimension | v1 (current) | v2 (target) |
|---|---|---|
| Document parsing | `pypdf` / `python-docx` only — fails on image PDFs | + Gemini Flash vision fallback when extracted text < 50 chars |
| Currency validation | None — LLM infers amount from raw text | Regex pre-pass → both regex amount + claimed amount fed to Intake |
| Policy evaluation | Single LLM call for all rules | Deterministic Python engine (hard rules) + Supervisor absorbs soft flags |
| Validation agent | Standalone agent — dead-end without session persistence | **Deleted**; merged as Supervisor 6th route |
| Approval agent | "Approval" — advocates for approving | **Renamed Critic** — adversarial framing, tries to reject first |
| Loop termination | `retry_count` + `_MAX_LOOPS` guard | + `supervisor_visits` hard counter; trips at 3 regardless of LLM output |
| Ledger seed data | 3 synthetic records — no traps for the agent | **80+ seeded records** with embedded fraud traps for demo |
| Graph topology | Linear: intel → policy → supervisor | **Parallel**: intel ∥ policy_check → supervisor |
| Subscription catalog | 6 active licenses, 6 catalog entries | **30–35 active licenses, 35+ catalog entries** |

---

## System Components (v2)

### 1. API Layer — `app/main.py` (FastAPI) — UNCHANGED

Same endpoints. The `document_parser` call now includes a vision fallback path.

### 2. Orchestration Layer — `app/graph.py` (LangGraph)

#### v2 Graph Topology

```
START → intake → [intelligence ∥ policy_check] → supervisor
                        ▲                              │
                        │  route_back_intel            ├── route_to_approval ──► critic
                        └──────────────────────────────┤
                          route_back_policy             ├──────────► policy_check → supervisor
                                                        │
                          request_user_clarification    ├──► clarify_node (terminal)
                                                        │
                          request_human_escalation      └──► escalate_node
                                                               │
                             critic ──────────────────────────►│
                             clarify_node ────────────────────►│
                             escalate_node ───────────────────►│
                                                               └──► recorder → END
```

#### Key Structural Changes

**Parallel Execution (Intelligence ∥ Policy_Check):**

LangGraph supports `Fan-Out / Fan-In` via `add_edge` from a single source to multiple targets. After `intake`, both `intelligence` and `policy_check` run simultaneously. A new `merge_intel_policy` passthrough node collects both outputs before `supervisor`.

```python
# In graph.py build_graph():
g.add_edge("intake", "intelligence")
g.add_edge("intake", "policy_check")          # NEW — parallel branch
g.add_edge("intelligence", "merge_intel_policy")
g.add_edge("policy_check", "merge_intel_policy")
g.add_edge("merge_intel_policy", "supervisor")
```

**Validation Node → Removed:**
- Nodes deleted: `validation`, `request_info`
- Routing function deleted: `_post_validation_route`
- New terminal node: `clarify_node` — packages `SupervisorDecision.clarification_questions` as `ApprovalOutcome(REQUEST_INFO)`

**Supervisor Routes (6 total):**
```python
class SupervisorRoute(str, Enum):
    route_to_approval           = "route_to_approval"
    route_back_to_intelligence  = "route_back_to_intelligence"
    route_back_to_policy        = "route_back_to_policy"
    request_human_escalation    = "request_human_escalation"
    request_user_clarification  = "request_user_clarification"   # replaces route_to_validation
```

**Loop Termination Guard:**
```python
# In supervisor_node:
visits = state.get("supervisor_visits", 0) + 1
if visits >= 3:
    force_escalate()  # no LLM call — deterministic exit
```

### 3. Agent Layer — Changes Summary

| Agent | File | Status |
|---|---|---|
| Intake | `app/agents/intake.py` | MODIFY — vision fallback + regex cross-check |
| Intelligence | `app/agents/intelligence.py` | MODIFY — tools emit pre-computed signals |
| Policy Engine | `app/tools/policy_engine.py` | **NEW** — deterministic hard-rule evaluator |
| Policy Agent | `app/agents/policy.py` | REMOVE (absorbed by policy_engine + Supervisor) |
| Supervisor | `app/agents/supervisor.py` | MODIFY — 6th route + `supervisor_visits` guard |
| Validation | `app/agents/validation.py` | **DELETE** |
| Critic (was Approval) | `app/agents/critic.py` | RENAME + adversarial framing |
| Recorder | `app/agents/recorder.py` | UNCHANGED |

### 4. Tooling Layer — Changes

| File | Status | Change |
|---|---|---|
| `document_parser.py` | MODIFY | Add vision fallback via Gemini Flash |
| `amount_extractor.py` | **NEW** | Regex currency extraction |
| `policy_engine.py` | **NEW** | Deterministic hard-rule Python evaluator |
| `ledger.py` | UNCHANGED | |
| `ledger_search.py` | MODIFY | Tools return pre-computed anomaly signals |
| `policy_store.py` | RETIRE | Superseded by `policy_engine.py` for hard rules |
| `subscription_catalog.py` | UNCHANGED | |

### 5. Observability — UNCHANGED

LangSmith tracing unchanged. The parallel `intelligence ∥ policy_check` branches will appear as sibling spans in the trace tree.

---

## Data Layer (v2)

### Ledger Seed — `data/ledger.json`

Current: 3 records. Required for demo: **80–100 records**.

Embedded fraud traps (required for Intelligence agent demo):

| Trap | Description | Records needed |
|---|---|---|
| **Duplicate claim** | Same employee, same vendor, same amount, 28 days apart | 2 records |
| **Uber spike** | Employee E007: 1 Uber ride/month for 5 months, then 4 in one week | 9 records |
| **Recurring SaaS** | Notion Plus claimed monthly by E003 for 6 months | 6 records |
| **Amount mismatch** | Claim for MYR 485 where receipt shows 48.50 (10x typo trap) | 1 record |
| **Clean baseline** | Legitimate claims across 15 employees | ~65 records |

See `plan/seed_data.md` for the exact JSON seed file.

### Subscription Catalog — `data/org_subscriptions.json`

Current: 5 active licenses, 6 catalog entries.
Required: **30 active licenses, 35 catalog entries** so `lookup_subscription_catalog` finds real matches.

### Policies — `data/policies.json`

No new rules required. The deterministic engine will evaluate the existing 8 rules.
Optional: Add `"layer": "hard"` / `"layer": "soft"` tags to each rule for clarity.

---

## Project Layout (v2)

```
orion/
├── app/
│   ├── main.py
│   ├── graph.py              ← MODIFY: parallel branches, remove validation, add clarify_node
│   ├── state.py              ← MODIFY: add supervisor_visits, remove validation field
│   ├── schemas.py            ← MODIFY: SupervisorRoute 6th value, SupervisorDecision questions field
│   │                                   remove ValidationReport/ClarificationRequest
│   ├── config.py             ← MODIFY: add GOOGLE_API_KEY for vision fallback
│   ├── llm.py                ← UNCHANGED
│   ├── agents/
│   │   ├── intake.py         ← MODIFY
│   │   ├── intelligence.py   ← MODIFY
│   │   ├── policy.py         ← REMOVE (replaced by policy_engine.py node)
│   │   ├── supervisor.py     ← MODIFY
│   │   ├── validation.py     ← DELETE
│   │   ├── critic.py         ← NEW (renamed from approval.py)
│   │   └── recorder.py       ← UNCHANGED
│   ├── tools/
│   │   ├── document_parser.py   ← MODIFY (vision fallback)
│   │   ├── amount_extractor.py  ← NEW
│   │   ├── policy_engine.py     ← NEW
│   │   ├── ledger.py            ← UNCHANGED
│   │   ├── ledger_search.py     ← MODIFY (pre-computed signals)
│   │   ├── policy_store.py      ← RETIRE (keep for compat, not used in graph)
│   │   └── subscription_catalog.py ← UNCHANGED
│   └── web/
│       └── index.html           ← MINOR: update agent names in UI trace display
├── data/
│   ├── ledger.json          ← REPLACE with 80+ seeded records
│   ├── org_subscriptions.json ← EXPAND to 30+ licenses + 35+ catalog
│   └── policies.json        ← OPTIONAL: add layer tags
├── docs/                    ← Existing documentation (unchanged)
├── plan/                    ← This directory
└── scripts/
    └── smoke.py             ← MODIFY: update for new graph shape
```

---

## Key Dependencies (v2)

| Package | Role | Status |
|---|---|---|
| `langgraph >= 1.0.2` | State graph, parallel fan-out | UNCHANGED |
| `langchain-core >= 1.1.0` | `@tool` decorator | UNCHANGED |
| `langsmith >= 0.1.140` | Tracing | UNCHANGED |
| `openai >= 1.40.0` | ILMU/GLM-5.1 client | UNCHANGED |
| `pydantic >= 2.8.0` | Schemas | UNCHANGED |
| `fastapi >= 0.115.0` | API layer | UNCHANGED |
| `rapidfuzz >= 3.9.0` | Fuzzy search | UNCHANGED |
| `pypdf >= 5.0.0` | PDF text extraction | UNCHANGED |
| `python-docx >= 1.1.2` | DOCX extraction | UNCHANGED |
| `google-generativeai >= 0.7.0` | **NEW** — Gemini Flash vision fallback | ADD |

---

## Pitch Points for Judges

1. **"We use adversarial agent review"** — Critic tries to reject; only approves when it can't find a counter-argument.
2. **"Parallel intelligence and policy"** — Intel and policy_check run simultaneously; we cut latency by ~40%.
3. **"Math never touches the LLM"** — Tools compute z-scores and duplicate signals; the LLM only narrates findings.
4. **"Loop termination is guaranteed"** — `supervisor_visits >= 3` forces deterministic escalation; demo never hangs.
5. **"Vision-aware intake"** — Image PDFs are handled via Gemini Flash; we scope to digital receipts but handle scans gracefully.
