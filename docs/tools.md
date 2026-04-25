# Orion Tools Reference — Current Implementation

All tools live under `app/tools/`. This document describes each file's
purpose and public API as implemented.

---

## `amount_extractor.py`

Regex-based currency extractor used by the Intake agent as an anti-hallucination
pre-pass. Runs before the LLM to anchor the amount extraction.

**Public API:**
```python
def extract_largest_amount(text: str) -> float | None
```
Scans `text` for currency tokens in the forms: `RM 123.45`, `MYR 123`, `$123`,
`USD 123`, `€123`, `£123`, `¥123`. Returns the largest numeric value found,
or `None` if no token is found.

```python
def amount_discrepancy_flag(
    regex_amount: float | None,
    claimed_amount: float,
    threshold_pct: float = 20,
) -> bool
```
Returns `True` if `regex_amount` is not `None` and the relative difference
between `regex_amount` and `claimed_amount` exceeds `threshold_pct` percent.
Used by Intake to force `confidence < 0.6` when amounts diverge.

---

## `document_parser.py`

Converts uploaded binary documents (PDF, DOCX, TXT) into raw text strings
for the Intake agent.

**Public API:**
```python
def parse_document(filename: str, content: bytes) -> ParsedDocument
```

- Uses `pypdf` for PDF, `python-docx` for DOCX, UTF-8 decode for TXT.
- Raises `UnsupportedDocumentError` for unknown extensions.
- Raises `DocumentTooLargeError` if `content` exceeds `settings.max_upload_bytes` (8 MB).

**`ParsedDocument`:** `filename: str`, `kind: str`, `text: str`, `page_count: int`, `bytes_read: int`

> **Limitation:** Digital PDFs only. Scanned/image-based PDFs produce empty text.

---

## `ledger.py`

Simple JSON-file ledger for persisting `LedgerRecord` entries.
Thread-safe via a `threading.Lock`.

**Public API:**
```python
class Ledger:
    def append(self, record: dict) -> None   # atomic write
    def all(self) -> list[dict]
    def by_employee(self, employee_id: str) -> list[dict]
```

**Data file:** `data/ledger.json` — `{"records": [...]}`

---

## `ledger_search.py` — Intelligence Agent Tools

Four `@tool`-decorated LangChain functions used in the Intelligence Agent's
tool-calling loop. All read from `data/ledger.json` and
`data/org_subscriptions.json`.

All tools return **pre-computed signals** alongside raw match data. The LLM
narrates and interprets these signals — it never calculates ratios or z-scores.

---

### `search_ledger_by_amount(amount, tolerance_pct=10.0, employee_id="")`

Finds past ledger records within ±`tolerance_pct`% of `amount` MYR.

**Returns:** JSON with `matches` (list of claim records) and `duplicate_signals`:
```json
{
  "matches": [...],
  "count": 2,
  "duplicate_signals": {
    "exact_duplicate_count": 1,
    "near_duplicate_count": 1,
    "same_employee_matches": 1,
    "last_seen_days_ago": 12
  }
}
```

---

### `search_ledger_by_merchant(merchant_name, employee_id="")`

Fuzzy substring search (rapidfuzz `partial_ratio ≥ 55%`) across `vendor` and
`product` fields of all ledger records.

**Returns:** JSON with `matches` and `vendor_signals`:
```json
{
  "matches": [...],
  "count": 5,
  "vendor_signals": {
    "recurring_pattern_detected": true,
    "claim_frequency_days": 30,
    "employee_claim_count": 2,
    "unique_employee_count": 4,
    "total_claims": 5
  }
}
```

---

### `search_employee_history(employee_id, days_back=90)`

Returns the employee's claim history within the last `days_back` calendar days,
plus an all-time total count and pre-computed anomaly signals.

**Returns:**
```json
{
  "employee_id": "E007",
  "days_back": 90,
  "recent_claims": [...],
  "total_in_window": 8,
  "all_time_total": 15,
  "anomaly_signals": {
    "spike_detected": true,
    "z_score": 3.2,
    "avg_weekly_rate": 0.8,
    "current_week_count": 4,
    "weeks_analyzed": 13
  }
}
```

---

### `lookup_subscription_catalog(merchant_name)`

Searches both the active org license list and the approved vendor catalog
by fuzzy substring match on vendor, product, and aliases.

**Returns:**
```json
{
  "matched_licenses": [...],
  "matched_catalog_entries": [...],
  "found_active": true,
  "found_in_catalog": true
}
```

Active license entries include: `id`, `vendor`, `product`, `owner_team`,
`seats_used`, `seats_total`, `seats_available`, `aliases`.

---

**Exported list for agent binding:**
```python
INTELLIGENCE_TOOLS = [
    search_ledger_by_amount,
    search_ledger_by_merchant,
    search_employee_history,
    lookup_subscription_catalog,
]
```

---

## `policy_engine.py`

Deterministic Python evaluator for hard corporate expense rules. No LLM — zero
hallucination risk, fully unit-testable.

**Public API:**
```python
def evaluate_hard_rules(
    claim: IntakeClaim,
    receipt_text: str,
    is_likely_duplicate: bool,
) -> HardPolicyResult
```

**Rules evaluated:**

| Rule ID | Condition | Effect |
|---|---|---|
| POL-004 | `business_justification` < 10 chars | Hard block → `fast_reject=True` |
| POL-005 | `category` not in approved list | Hard block → `fast_reject=True` |
| POL-007 | `amount_myr > 100` and `receipt_text` empty | Hard block → `fast_reject=True` |
| POL-006 | `is_likely_duplicate=True` | Hard block → `fast_reject=True` |
| POL-008 | Monthly billing period and `amount_myr > 200` | Soft flag (prefer annual) |
| Confidence | `intake.confidence < 0.6` | Soft flag |

**Amount-tier routing hints** (advisory, surfaced to Supervisor/Critic):
- ≤ MYR 500 → `auto_approve_eligible`
- MYR 500–5000 → `manager_approval_required`
- > MYR 5000 → `finance_approval_required`

**`HardPolicyResult` fields:**
- `hard_violations: list[PolicyViolation]`
- `routing_hints: list[str]`
- `ambiguous_flags: list[str]`
- `fast_reject: bool`

---

## `policy_store.py`

> **Status: Retained for backward compatibility — not used in the main graph.**

Loads `data/policies.json` and formats rules as a structured prompt block.
The main graph uses `policy_engine.py` (deterministic Python) instead.

**Public API:**
```python
class PolicyStore:
    def hard_rules(self) -> list[dict]
    def soft_rules(self) -> list[dict]
    def all(self) -> list[dict]
    def by_rule_id(self, rule_id: str) -> dict | None
    def as_prompt_block(self) -> str   # formatted rule list for LLM injection
```

---

## `subscription_catalog.py`

Loads `data/org_subscriptions.json`. Used by the Intelligence agent for the
initial catalog overview (injected into the investigation seed message) and
for fuzzy pre-filtering in `lookup_subscription_catalog`.

**Public API:**
```python
class SubscriptionCatalog:
    def active_licenses(self) -> list[dict]
    def approved_catalog(self) -> list[dict]
    def fuzzy_candidates(self, query: str, *, top_k: int = 5) -> list[dict]
    def as_prompt_block(self) -> str
```

`fuzzy_candidates` uses `rapidfuzz.fuzz.partial_ratio` with a threshold of 55
to produce a shortlist. The final duplicate decision is always made by the LLM.

---

## Data File Schemas

### `data/ledger.json`

```json
{
  "records": [
    {
      "claim_id": "CLM-XXXXXXXX",
      "employee_id": "E001",
      "vendor": "Notion Labs Inc.",
      "product": "Notion Plus",
      "amount_myr": 250.0,
      "decision": "auto_approve",
      "recorded_at": "2026-04-25T10:00:00+00:00",
      "notification_sent_to": ["employee:E001", "role:finance_ops"],
      "submission_hash": "abc123..."
    }
  ]
}
```

The ledger ships with 80+ seed records containing embedded fraud traps:
duplicate claims, spending spikes, recurring patterns, and clean baseline records.

### `data/org_subscriptions.json`

```json
{
  "active_licenses": [
    {
      "id": "ORG-001",
      "vendor": "Notion Labs Inc.",
      "product": "Notion Team Plan",
      "owner_team": "Operations",
      "seats_used": 45,
      "seats_total": 50,
      "seats_available": 5,
      "aliases": ["Notion", "Notion Plus", "Notion Business"]
    }
  ],
  "approved_catalog": [
    {
      "product": "Notion",
      "vendor": "Notion Labs Inc.",
      "category": "productivity",
      "note": "Approved — use org license. Individual purchase requires pre-approval."
    }
  ]
}
```

Ships with 30+ active licenses and an approved vendor catalog covering
common SaaS categories (productivity, engineering, comms, data, security).
