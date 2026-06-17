# Orion — One Hit Wonder

> AI-powered SaaS reimbursement assistant for modern teams.

Orion automates the end-to-end expense reimbursement workflow using a multi-agent AI pipeline. Employees submit claims in natural language; a chain of specialised agents extracts, validates, cross-references, and approves or escalates each claim — all without manual triage.

---

## Demo Video

<!-- Paste your Google Drive link below once the recording is ready -->

| Resource | Link |
|----------|------|
| Demo & Pitch Video (10 min) | https://drive.google.com/drive/folders/1uS_SWztFofZyJsnMjqxJLOxFHvmt5pCQ?usp=sharing |

---

## Team — One Hit Wonder

| Name | Role |
|------|------|
| David Huang | Tech Lead / Backend |
| Vanessa Serenina Prawirayasa | Product Manager / PRD |
| Jason Clarence Setya BUdi | QA Lead |
| Darren Cornelius Suwandi | Design / Pitch |

---

## What It Does

An employee submits a reimbursement claim — either typed in natural language or with an uploaded PDF/DOCX receipt. Orion's LangGraph workflow routes the claim through six AI agents:

1. **Intake** — extracts vendor, amount, category, and billing period
2. **Intelligence** — detects duplicates and suggests cheaper org-licensed alternatives
3. **Policy** — checks against company rules (spend limits, approved categories, justification)
4. **Validation** — flags missing information and generates clarification questions
5. **Approval** — issues a five-way decision (auto-approve, auto-reject, escalate manager, escalate finance, request info)
6. **Recorder** — writes the decision to the ledger and dispatches notifications

---

## Tech Stack

### Backend
| Layer | Technology |
|-------|-----------|
| API server | FastAPI |
| Workflow engine | LangGraph |
| LLM | ILMU GLM-5.1 (OpenAI-compatible) |
| Observability | LangSmith |
| Data validation | Pydantic v2 |
| Fuzzy matching | rapidfuzz |
| Document parsing | pypdf, python-docx |

### Frontend
| Layer | Technology |
|-------|-----------|
| UI framework | React 19 + TypeScript 5.8 |
| Build tool | Vite 6.2 |
| Routing | React Router DOM v7 |
| Styling | Tailwind CSS v4 |
| Animation | Motion (Framer Motion) v12 |
| Icons | Lucide React |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- An ILMU API key (set in `.env`)

### Backend
```bash
pip install -r requirements.txt
cp .env.example .env   # add your ILMU_API_KEY and ORION_API_KEYS
python main.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev            # runs on http://localhost:3000
```

---

## Security

| Control | Implementation |
|---------|----------------|
| **API Authentication** | All write endpoints (`POST /api/submit`, `POST /api/parse-document`, `DELETE /api/ledger`) require an `X-API-Key` header (or `?api_key=` query param). Configured via `ORION_API_KEYS` (comma-separated list). |
| **Rate Limiting** | Sliding-window per-IP limiter: 10 req/60 s on `/api/submit`, 120 req/60 s on all other `/api/*` routes. Returns `HTTP 429` with `Retry-After` header. |
| **Input Sanitisation** | All free-text fields are scanned for prompt-injection patterns before entering the workflow. Fields exceeding length caps are silently truncated. |

To generate a production API key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Then set `ORION_API_KEYS=<your-key>` in `.env`.

Send it in requests:
```bash
curl -H "X-API-Key: <your-key>" http://localhost:8000/api/submit ...
```

---

## Project Structure

```
orion/
├── .github/
│   └── workflows/
│       ├── ci.yml                        # PR gate — lint, unit, integration, coverage
│       └── nightly.yml                   # Scheduled live regression against real APIs
│
├── backend/                              # Python backend (FastAPI + LangGraph)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── critic.py                     # Approval / adversarial decision agent
│   │   ├── intake.py                     # Claim extraction agent
│   │   ├── intelligence.py               # Duplicate detection & alternative suggestion agent
│   │   ├── recorder.py                   # Ledger write & notification agent
│   │   └── supervisor.py                 # Routing & clarification agent
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── amount_extractor.py           # Regex currency pre-pass (anti-hallucination)
│   │   ├── document_parser.py            # PDF / DOCX / TXT text extraction
│   │   ├── ledger.py                     # JSON ledger read/write
│   │   ├── ledger_search.py              # LangChain tools for Intelligence agent
│   │   ├── policy_engine.py              # Deterministic policy rule evaluator
│   │   ├── policy_store.py               # Policy JSON loader
│   │   └── subscription_catalog.py       # Org SaaS catalog + fuzzy candidate search
│   ├── config.py                         # Pydantic settings (ILMU, LangSmith, thresholds)
│   ├── graph.py                          # LangGraph workflow assembly & conditional edges
│   ├── llm.py                            # ILMU GLM-5.1 client with retry & JSON-mode
│   ├── main.py                           # FastAPI entrypoint & API endpoints
│   ├── schemas.py                        # Pydantic contracts for all agent I/O
│   └── state.py                          # Shared WorkflowState TypedDict
│
├── frontend/                             # React SPA frontend
│   ├── e2e/
│   │   └── login.spec.ts                 # Playwright E2E tests
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts                 # Typed fetch client for all backend endpoints
│   │   │   └── types.ts                  # Request / response TypeScript types
│   │   ├── components/
│   │   │   └── DashboardElements.tsx     # BentoCard, Skeleton, StatusBadge
│   │   ├── context/
│   │   │   ├── AuthContext.tsx           # Role & username state
│   │   │   └── ToastContext.tsx          # Global toast notifications
│   │   ├── lib/
│   │   │   └── utils.ts                  # clsx / tailwind-merge helpers
│   │   ├── pages/
│   │   │   ├── HeroPage.tsx              # Role-based login landing page
│   │   │   ├── EmployeeDashboard.tsx     # Claim submission wizard + history
│   │   │   ├── ManagerDashboard.tsx      # Swipe-to-approve card interface
│   │   │   └── FinanceDashboard.tsx      # Ledger table + policy + analytics
│   │   ├── test/                         # Frontend unit tests
│   │   ├── App.tsx                       # SPA router (/, /employee, /manager, /finance)
│   │   ├── constants.ts                  # Shared mock data and constants
│   │   ├── index.css                     # Tailwind base styles
│   │   └── main.tsx                      # React entry point
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── vitest.config.ts
│
├── data/
│   ├── ledger.json                       # Persistent claim records
│   ├── org_subscriptions.json            # Org-wide SaaS license catalog
│   └── policies.json                     # Reimbursement policy rules
│
├── docs/
│   ├── agents.md                         # Per-agent responsibilities and schemas
│   ├── architecture.md                   # System components and data flow
│   ├── tools.md                          # Tool implementations and contracts
│   └── workflow.md                       # Execution guide and graph topology
│

├── scripts/
│   ├── gen_claims.py                     # Synthetic claim generator for testing
│   └── smoke.py                          # Offline smoke test with canned LLM responses
│
├── tests/
│   ├── fixtures/
│   │   ├── expected.yaml                 # Decision-band assertions for regression tests
│   │   └── payloads.py                   # Reusable submission payloads
│   ├── integration/
│   │   ├── test_api_endpoints.py         # FastAPI endpoint integration tests
│   │   ├── test_workflow_live.py         # Live ILMU + LangSmith tests (--runlive flag)
│   │   └── test_workflow_stub.py         # Full graph tests with stubbed LLM
│   ├── unit/
│   │   ├── test_amount_extractor.py
│   │   ├── test_document_parser.py
│   │   ├── test_graph_routes.py
│   │   ├── test_ledger.py
│   │   ├── test_ledger_search.py
│   │   ├── test_policy_engine.py
│   │   ├── test_policy_store.py
│   │   ├── test_schemas.py
│   │   └── test_subscription_catalog.py
│   └── conftest.py                       # Shared fixtures, stub LLM, --runlive flag
│
├── .env.example                          # Environment variable template
├── pytest.ini                            # Pytest config (coverage gate, markers)
├── requirements.txt                      # Production dependencies
├── requirements-dev.txt                  # Development / test dependencies
└── README.md
```

---

## Running Tests

### Backend
```bash
python -m pytest --cov=backend --cov-fail-under=80 -q
```

Current coverage: **85%** — 120 passed, 4 skipped (live API tests).

### Frontend — Unit Tests (Vitest)
```bash
cd frontend
npm install
npm test              # single run
npm run test:watch    # watch mode during development
npm run test:coverage # with coverage report
```

Test files live in `src/test/`. Current suites:

| File | What it tests |
|------|---------------|
| `api.client.test.ts` | All API client functions (fetchLedger, submitClaim, deleteClaim, clearHistory, parseDocument) — happy paths, error codes 401/403/413/415/422/429 |
| `HeroPage.test.tsx` | Role selection, form validation, auth-code toggle, navigation |

### Frontend — E2E Tests (Playwright)
```bash
cd frontend
npm install
npx playwright install chromium   # first time only
npm run test:e2e                   # headless
npm run test:e2e:ui                # interactive UI runner
```

E2E specs live in `e2e/`. Current suites:

| File | Scenarios |
|------|-----------|
| `login.spec.ts` | Landing page, role selection, empty-form validation, valid employee/manager/finance login, auth-code show/hide toggle |

---

## Known Limitations

| Limitation | Detail |
|------------|--------|
| Digital receipts only | Scanned or image-based PDFs return empty text; employees must upload digitally-generated PDFs or paste receipt text manually. |
| No session persistence | If the workflow routes to `request_info`, the graph terminates and a new submission is required. |
| Single-tenant ledger | The ledger is a flat JSON file scoped to one organisation — demo use only. |
| GLM-5.1 only | The LLM client targets the ILMU endpoint; swapping to another provider requires changing `backend/llm.py`. |

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/architecture.md](docs/architecture.md) | System components, project layout, and data flow |
| [docs/agents.md](docs/agents.md) | Per-agent responsibilities, tools, and I/O schemas |
| [docs/workflow.md](docs/workflow.md) | Step-by-step execution guide, graph topology, and **sequence diagrams** |
| [docs/tools.md](docs/tools.md) | Tool implementations and data contracts |
