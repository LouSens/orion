# orion - Technical Documentation

This directory contains technical documentation that reflects the **current code state** of the Orion system.

| Document | Description |
|---|---|
| [architecture.md](docs/architecture.md) | System components, project layout, and data flow |
| [agents.md](docs/agents.md) | Per-agent responsibilities, tools, and I/O schemas |
| [workflow.md](docs/workflow.md) | Step-by-step execution guide and graph topology |
| [tools.md](docs/tools.md) | Tool implementations and data contracts |

> **Note:** The canonical source of truth for the *intended design* is `plan/`. These docs in `docs/` reflect what is actually implemented in code. The v2 plan has been fully implemented.

---

## v2 Changes at a Glance

The following changes were made from the original v1 design:

| Area | v1 | v2 (current) |
|---|---|---|
| **Policy evaluation** | LLM agent (`policy.py`) | Deterministic Python (`policy_engine.py`) |
| **Graph topology** | Linear: intake → intelligence → policy → supervisor | Parallel: `[intelligence ∥ policy_check]` after intake |
| **Fast-reject** | Not present | Short-circuits to Critic on any hard violation, skipping Supervisor |
| **Validation agent** | Separate `validation.py` agent | Removed; merged into Supervisor's `request_user_clarification` route |
| **Approval agent** | Neutral `approval.py` | Renamed to `critic.py`; adversarial framing (tries to reject first) |
| **Loop protection** | `retry_count` ceiling | `supervisor_visits` counter; ≥ 3 forces `request_human_escalation` |
| **Intelligence tools** | Return raw matches only | Return pre-computed signals (z-score, spike flag, duplicate counts) |
| **Intake** | LLM extraction only | Regex currency pre-pass before LLM (anti-hallucination guard) |
| **Idempotency** | Not present | SHA-256 submission hash; duplicate POSTs return cached result |

---

## Known Limitations

These are intentional scope decisions, not bugs. Mention them proactively during the demo.

| Limitation | Detail | Workaround |
|---|---|---|
| **Digital receipts only** | The document parser (`pypdf`, `python-docx`) extracts embedded text only. Scanned receipts or image-based PDFs return empty text. | Employees must upload digitally-generated PDFs (e.g., from Stripe, Notion, GitHub billing) or paste the receipt text into the free-text field. |
| **No session persistence** | The workflow executes end-to-end in a single LangGraph run. There is no "pause and resume" — if the Supervisor routes to `request_user_clarification`, the graph terminates and a new submission is required. | The clarification questions are returned in the API response for the frontend to display. |
| **Single-tenant ledger** | The ledger is a flat JSON file with no multi-tenancy or per-org isolation. | Scope is single-organisation demo only. |
| **GLM-5.1 only** | The LLM client is hardcoded to the ILMU/GLM-5.1 endpoint. Swapping to GPT-4o or Claude requires changing `app/llm.py`. | Replace `chat_structured()` client config. |
