# Orion Reimburse — Test Strategy (MVP)

A pragmatic, low-cost test plan for an agentic workflow. Real LLM calls are
expensive and flaky, so the suite is split between fast deterministic tests
(the majority) and a small number of opt-in live tests against ILMU GLM-5.1.

All test code lives under [`tests/`](tests/). Run `pytest -ra` to execute the
default offline suite; pass `--runlive` to additionally hit the real APIs.

---

## 1. Scope & Requirements Traceability

The original brief defined ten requirements. Every one is anchored to specific
production code and to one or more tests so a regression cannot slip through
unnoticed, and so any unrelated feature creep stands out as "tests against an
unmapped requirement."

### Requirements Traceability Matrix (RTM)

| ID  | Requirement | Code under test | Test files |
|---:|---|---|---|
| **R1** | End-to-end subscription-reimbursement claim handling. | [app/main.py](app/main.py), [app/graph.py](app/graph.py) | [test_workflow_stub.py](tests/integration/test_workflow_stub.py), [test_api_endpoints.py](tests/integration/test_api_endpoints.py) |
| **R2** | Multi-agent orchestration: Intake, Intelligence, Policy, Supervisor, Critic, Recorder with structured pydantic contracts. | [app/agents/](app/agents), [app/schemas.py](app/schemas.py) | [test_schemas.py](tests/unit/test_schemas.py), [test_workflow_stub.py](tests/integration/test_workflow_stub.py) |
| **R3** | Adaptive supervisor routing — fast-reject, 5-way LLM routing, loop-back, hard termination guard. | [app/graph.py](app/graph.py) (`_fast_reject_route`, `_supervisor_route`), [app/agents/supervisor.py](app/agents/supervisor.py), [app/tools/policy_engine.py](app/tools/policy_engine.py) | [test_graph_routes.py](tests/unit/test_graph_routes.py), [test_policy_engine.py](tests/unit/test_policy_engine.py) |
| **R4** | Intelligence agent — semantic duplicate detection, alternative suggestion, organisational cross-referencing via tool calls. | [app/agents/intelligence.py](app/agents/intelligence.py), [app/tools/ledger_search.py](app/tools/ledger_search.py), [app/tools/subscription_catalog.py](app/tools/subscription_catalog.py) | [test_ledger_search.py](tests/unit/test_ledger_search.py), `test_workflow_stub.py::test_scenario_lands_in_expected_band[duplicate]` and `[semantic_dup]` |
| **R5** | Ambiguity & incomplete-data handling — `clarify` route emits REQUEST_INFO with targeted questions. | [app/graph.py](app/graph.py) (`clarify_node`, `escalate_node`) | [test_graph_routes.py::TestClarifyNode](tests/unit/test_graph_routes.py), [test_graph_routes.py::TestEscalateNode](tests/unit/test_graph_routes.py) |
| **R6** | Reliability & idempotency — recorder persistence, submission-hash dedup, ledger thread-safety. | [app/main.py](app/main.py) (`_submission_hash`), [app/agents/recorder.py](app/agents/recorder.py), [app/tools/ledger.py](app/tools/ledger.py) | [test_ledger.py](tests/unit/test_ledger.py), `test_api_endpoints.py::test_submit_idempotency_returns_cached`, `test_workflow_stub.py::test_recorder_writes_ledger_entry` |
| **R7** | ILMU GLM-5.1 production LLM client with retries, timeouts, structured-output fallback. | [app/llm.py](app/llm.py) | [test_workflow_live.py](tests/integration/test_workflow_live.py) (only path that actually hits the API) |
| **R8** | LangGraph wiring + LangSmith deep-link surfacing. | [app/graph.py](app/graph.py), [app/main.py](app/main.py) (`_langsmith_refs`) | `test_api_endpoints.py::test_submit_returns_decision_and_langsmith_block`, `test_workflow_live.py::test_live_scenario_within_band_and_sla` |
| **R9** | Demo UI surface — workflow diagram, document upload, ledger view, audit export. | [app/web/index.html](app/web/index.html), [app/main.py](app/main.py) (`/api/parse-document`, `/api/audit/*`), [app/tools/document_parser.py](app/tools/document_parser.py) | [test_document_parser.py](tests/unit/test_document_parser.py), `test_api_endpoints.py::test_parse_document_*`, `::test_audit_csv_export`, `::test_audit_report_markdown` |
| **R10** | Latency / hallucination controls — per-agent LLM config, deterministic regex amount anchor. | [app/config.py](app/config.py) (`AgentLLMConfig`, `cfg_*`), [app/tools/amount_extractor.py](app/tools/amount_extractor.py) | [test_amount_extractor.py](tests/unit/test_amount_extractor.py) |

### How traceability is enforced

- **Forward direction** — every requirement above must list at least one test path. A new requirement (e.g. an MCP-published Notion writer) opens a PR that adds a row here AND a test, in the same change.
- **Backward direction** — every test belongs to a requirement. A reviewer who sees a new test that doesn't slot under R1–R10 should flag it: either the requirement list needs a new row (legitimate scope expansion), or the test is unplanned feature creep and should be cut.
- **Audit hook** — a future CI step can grep this file for the expected test references; a missing reference fails the matrix-coverage check. (Out of scope for the MVP build, but the file is structured to support it.)

---

## 2. Unit tests

| | |
|--|--|
| **Scope** | Pure functions and routing primitives in isolation: `app/tools/*` (`amount_extractor`, `policy_engine`, `policy_store`, `ledger`, `ledger_search`, `document_parser`), `app/schemas.py` validators, the supervisor routers and non-LLM graph nodes in `app/graph.py` (`_fast_reject_route`, `_supervisor_route`, `clarify_node`, `escalate_node`, `merge_intel_policy_node`). |
| **Execution** | `pytest tests/unit -ra` — runs in under 3 s on a laptop. No network, no LLM, no LangSmith export. |
| **Isolation** | The `stub_llm` fixture in [`tests/conftest.py`](tests/conftest.py) replaces `app.llm.chat_structured` and `app.llm.chat` with deterministic fakes that return canned pydantic objects per scenario. The `tmp_data_dir` fixture seeds a fresh temp directory with copies of `data/policies.json` + `data/org_subscriptions.json`, redirects `settings.data_dir`, and rebinds the `path` attribute on every module-level `Ledger()` instance. |
| **Pass condition** | All assertions green; ≥ **80 %** line coverage on `app/` excluding `app/web/`. The default offline suite currently records **80 %** at 95 passing tests. |

What we explicitly DO NOT unit-test: prompt content, JSON schema injection,
or model behaviour. Those belong to integration.

---

## 3. Integration tests

| | |
|--|--|
| **Scope** | The full LangGraph workflow end-to-end plus the FastAPI HTTP layer (`/api/health`, `/api/submit`, `/api/parse-document`, `/api/ledger`, `/api/audit/export`, `/api/audit/report`). Validates wiring, state propagation, conditional edges, ledger persistence, idempotency cache, and JSON serialization. |
| **Execution** | Default (`pytest tests/integration -ra`) runs the stub-LLM mode in roughly 1 s. Live mode (`pytest --runlive tests/integration/test_workflow_live.py`) hits the real ILMU + LangSmith APIs and takes 3-5 minutes for the four scenarios. |
| **Workflow** | For each scenario in [`tests/fixtures/payloads.py`](tests/fixtures/payloads.py) the test posts to `/api/submit`, then asserts the trace contains the expected nodes, the trace excludes the unwanted ones, and `approval.decision` matches the band declared in [`tests/fixtures/expected.yaml`](tests/fixtures/expected.yaml). The live mode additionally asserts a non-null `langsmith.run_id` when tracing is enabled. |
| **Pass condition** | Stub mode: 100 % of scenarios pass. Live mode: ≥ **75 %** of scenarios in band per run, with a 120 s per-claim SLA. The live suite is allowed one re-run on a single flake. |

---

## 4. Test environment & CI/CD practice

| Stage | Where | What runs |
|--|--|--|
| **Local** | Developer laptop. Install with `pip install -r requirements.txt -r requirements-dev.txt`. | `pytest -ra` for the offline suite (≈ 2 s). Live mode invoked manually before pushing risky changes to prompts or schemas. |
| **Staging / CI** | GitHub Actions [.github/workflows/ci.yml](.github/workflows/ci.yml), ubuntu-latest, Python 3.12. | On every PR and push to `main`: full offline suite via `pytest -ra --cov=app --cov-fail-under=80`. Secrets `ILMU_API_KEY` / `LANGSMITH_API_KEY` are NOT exposed; the workflow exports `ILMU_API_KEY=dev-key` to force the stub path. Total budget ≤ 5 min. |
| **CI/CD automated pipeline** | GitHub Actions [.github/workflows/nightly.yml](.github/workflows/nightly.yml), cron 02:00 UTC + manual dispatch. | Live integration tests against ILMU staging key. Failures page on-call only on 2+ consecutive reds (avoids flake noise). |

Promotion rule: a change reaches `main` only after green offline CI on PR; a release tag requires the most recent nightly to be green.

---

## 5. Regression testing & pass/fail rules

| | |
|--|--|
| **Execution phase** | Offline regression runs on every PR (CI). Live regression runs nightly + before any release tag. The same scripted scenarios from §3 are reused as the regression baseline; expected decision bands and required trace nodes are committed to [`tests/fixtures/expected.yaml`](tests/fixtures/expected.yaml). |
| **Pass condition** | (a) Every scenario terminates (no exceptions, no timeouts > 120 s). (b) `approval.decision` lands in its expected band. (c) The trace contains every node in `trace_includes` and none in `trace_excludes` — this catches accidental skips of supervisor / critic / recorder. (d) Live mode: `langsmith.run_id` is populated when tracing is on. |
| **Fail condition** | Any scenario raises an unhandled exception, or 2+ scenarios produce out-of-band decisions, or any scenario exceeds the 120 s SLA. |
| **Continuation rule** | A single flaked scenario does NOT block the release — it is logged and the suite re-runs once. Two reds in a row blocks the release and opens an issue auto-tagged `regression`. Prompt or schema changes that intentionally move a scenario into a new band MUST update `expected.yaml` in the same PR; an unjustified band change is itself treated as a regression. |

---

## 6. Test data strategy

| Source | Purpose | Lifecycle |
|--|--|--|
| **Manual fixtures** ([tests/fixtures/payloads.py](tests/fixtures/payloads.py)) | Four scripted `ReimbursementSubmission` scenarios — `clean`, `duplicate` (Notion), `semantic_dup` (ChatGPT), `high_value` (Datadog annual). Each exercises a distinct routing path: clean → critic → auto_approve; duplicate → fast-reject; semantic_dup → suggest_alternative → escalate_manager; high_value → escalate_finance. | Versioned with the code. Adding a new routing path requires a new entry plus a row in `expected.yaml`. |
| **Org-state fixtures** ([data/org_subscriptions.json](data/org_subscriptions.json), [data/policies.json](data/policies.json)) | The `tmp_data_dir` fixture copies these into the test sandbox so the Intelligence + Policy agents see a stable world even if the live data files drift during demos. | Refreshed when a policy rule or org licence is added. |
| **Automated / synthetic** ([scripts/gen_claims.py](scripts/gen_claims.py)) | Generator that emits N perturbed claims by varying vendor casing, currency, and amount around policy thresholds (100 / 500 / 5000 / 7800 MYR). Used in nightly live soak runs to surface threshold-edge regressions. Output is JSONL (stdout or `--out`); the payloads themselves are not committed — only the pass/fail summary is. | Regenerated each nightly run; deterministic via `--seed`. |
| **PII** | None. All employee names/IDs are fictitious. Receipt text is hand-written. No real customer data ever enters the suite. | — |

---

## 7. Passing-rate thresholds

| Suite | Threshold | If below |
|--|--|--|
| Unit | **100 %** must pass | Block PR merge. |
| Integration (stub) | **100 %** must pass | Block PR merge. |
| Integration (live) | **≥ 75 %** scenarios in band per run, **≥ 90 %** rolling over the last 5 nightly runs | Single dip → re-run once. Rolling < 90 % → block release, open `regression` issue. |
| Coverage (unit + stub-integration) | **≥ 80 %** line coverage on `app/` excluding `app/web/` | CI hard-fails via `--cov-fail-under=80`. |

Headline KPI: **green-merge rate ≥ 95 % over a rolling 14-day window.** Below
that threshold the team pauses feature work and invests one cycle in suite
hardening.

---

## Appendix — Running the suite

```bash
# Offline: unit + stub-integration. ~2s.
pip install -r requirements.txt -r requirements-dev.txt
pytest -ra

# With coverage (matches CI):
pytest -ra --cov=app --cov-report=term-missing --cov-fail-under=80

# Live (requires real .env with ILMU_API_KEY + LANGSMITH_API_KEY):
pytest --runlive tests/integration/test_workflow_live.py

# Synthetic soak (writes 50 claims as JSONL):
python -m scripts.gen_claims --count 50 --out tmp/synth.jsonl
```
