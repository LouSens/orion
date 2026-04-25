"""Ledger search tools for the Intelligence Agent's tool-calling loop.

Four LangChain-compatible tools that the Intelligence agent's LLM can
invoke in any order, any number of times (up to the iteration cap), to
build up evidence before producing its final IntelligenceReport.

Each tool reads from the JSON ledger (data/ledger.json) and the
org subscriptions catalog (data/org_subscriptions.json) — no network
calls, so they're fast and deterministic.

v2: Each tool returns pre-computed anomaly signals alongside raw data.
The LLM narrates findings — it never recalculates.

Tools:
    search_ledger_by_amount      — finds past claims near a given MYR value
    search_ledger_by_merchant    — finds past claims from the same vendor
    search_employee_history      — checks recent claim volume for one employee
    lookup_subscription_catalog  — checks if merchant is a known org SaaS
"""
from __future__ import annotations

import datetime
import json
import statistics
from datetime import timedelta, timezone
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool
from rapidfuzz import fuzz as _fuzz

from ..config import settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_ledger() -> list[dict]:
    path = settings.data_dir / "ledger.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("records", [])


def _load_catalog() -> dict:
    path = settings.data_dir / "org_subscriptions.json"
    if not path.exists():
        return {"active_licenses": [], "approved_catalog": []}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Signal computation helpers (pure Python — no LLM)
# ---------------------------------------------------------------------------

def _compute_spike_signals(claims: list[dict], days_back: int) -> dict:
    """Z-score based weekly spike detection."""
    if not claims:
        return {
            "spike_detected": False, "z_score": 0.0,
            "avg_weekly_rate": 0.0, "current_week_count": 0,
            "is_anomaly": False, "weeks_analyzed": 0,
        }

    week_counts: dict[str, int] = {}
    for c in claims:
        try:
            dt = datetime.datetime.fromisoformat(c["recorded_at"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        week_key = dt.strftime("%Y-W%W")
        week_counts[week_key] = week_counts.get(week_key, 0) + 1

    if not week_counts:
        return {
            "spike_detected": False, "z_score": 0.0,
            "avg_weekly_rate": 0.0, "current_week_count": 0,
            "is_anomaly": False, "weeks_analyzed": 0,
        }

    counts = list(week_counts.values())
    if len(counts) < 2:
        return {
            "spike_detected": False, "z_score": 0.0,
            "avg_weekly_rate": counts[0],
            "current_week_count": counts[0],
            "is_anomaly": False, "weeks_analyzed": len(counts),
        }

    mean = statistics.mean(counts)
    stdev = statistics.stdev(counts) or 0.001
    current_week = max(week_counts, key=week_counts.get)
    current_count = week_counts[current_week]
    z_score = (current_count - mean) / stdev

    return {
        "spike_detected": z_score > 2.0,
        "z_score": round(z_score, 2),
        "avg_weekly_rate": round(mean, 2),
        "current_week_count": current_count,
        "is_anomaly": z_score > 2.0,
        "weeks_analyzed": len(counts),
    }


def _compute_duplicate_signals(
    matches: list[dict],
    employee_id: str,
    amount: float,
    tolerance_pct: float = 1.0,
) -> dict:
    """Exact/near duplicate counts and last-seen-days for amount matches."""
    if not matches:
        return {
            "exact_duplicate_count": 0, "near_duplicate_count": 0,
            "same_employee_matches": 0, "last_seen_days_ago": None,
        }

    same_emp = [m for m in matches if m.get("employee_id") == employee_id]
    now = datetime.datetime.utcnow()
    days_ago = None
    if matches:
        try:
            latest = max(matches, key=lambda m: m.get("recorded_at", ""))
            dt = datetime.datetime.fromisoformat(latest["recorded_at"].replace("Z", "+00:00"))
            days_ago = (now - dt.replace(tzinfo=None)).days
        except (ValueError, KeyError):
            pass

    def _within_tolerance(m: dict) -> bool:
        match_amt = m.get("amount_myr", 0)
        if amount == 0:
            return match_amt == 0
        return abs(match_amt - amount) / amount * 100 <= tolerance_pct

    return {
        "exact_duplicate_count": len([m for m in matches if _within_tolerance(m)]),
        "near_duplicate_count": len(matches),
        "same_employee_matches": len(same_emp),
        "last_seen_days_ago": days_ago,
    }


def _compute_vendor_signals(matches: list[dict], employee_id: str) -> dict:
    """Vendor frequency and per-employee claim signals."""
    if not matches:
        return {
            "recurring_pattern_detected": False, "claim_frequency_days": None,
            "employee_claim_count": 0, "unique_employee_count": 0, "total_claims": 0,
        }

    # How many times THIS employee has claimed from this vendor
    employee_claim_count = len([m for m in matches if m.get("employee_id") == employee_id])
    unique_employees = len({m.get("employee_id") for m in matches if m.get("employee_id")})

    sorted_claims = sorted(matches, key=lambda m: m.get("recorded_at", ""))
    avg_interval = None
    recurring = False
    if len(sorted_claims) >= 2:
        try:
            dates = [
                datetime.datetime.fromisoformat(m["recorded_at"].replace("Z", "+00:00"))
                for m in sorted_claims
            ]
            intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
            avg_interval = statistics.mean(intervals) if intervals else None
            recurring = avg_interval is not None and avg_interval < 35
        except (ValueError, KeyError):
            pass

    return {
        "recurring_pattern_detected": recurring,
        "claim_frequency_days": round(avg_interval, 1) if avg_interval is not None else None,
        "employee_claim_count": employee_claim_count,
        "unique_employee_count": unique_employees,
        "total_claims": len(matches),
    }


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@tool
def search_ledger_by_amount(amount: float, tolerance_pct: float = 10.0, employee_id: str = "") -> str:
    """Search the expense ledger for past claims with a similar MYR amount.

    Args:
        amount: The target amount in MYR to search around.
        tolerance_pct: Percentage tolerance band (default 10%). E.g. 10.0 means ±10%.
        employee_id: Current claimant's employee ID for duplicate signal computation.

    Returns:
        JSON string listing matching records plus pre-computed duplicate_signals.
    """
    if amount is None or amount <= 0:
        return json.dumps({"matches": [], "note": "amount must be positive"})

    low = amount * (1 - tolerance_pct / 100)
    high = amount * (1 + tolerance_pct / 100)
    records = _load_ledger()
    matches = [
        {k: r[k] for k in ("claim_id", "vendor", "product", "amount_myr", "employee_id", "decision", "recorded_at") if k in r}
        for r in records
        if low <= r.get("amount_myr", -1) <= high
    ]
    signals = _compute_duplicate_signals(matches, employee_id=employee_id, amount=amount)
    return json.dumps({"matches": matches, "count": len(matches), "duplicate_signals": signals})


@tool
def search_ledger_by_merchant(merchant_name: str, employee_id: str = "") -> str:
    """Search the expense ledger for past claims from the same merchant/vendor.

    Uses rapidfuzz partial_ratio matching (threshold from config) so variant
    spellings are captured (e.g. 'Notion' matches 'Notion Labs Inc.').

    Args:
        merchant_name: Vendor name or product name to search for.
        employee_id: Current claimant's employee ID for vendor signal computation.

    Returns:
        JSON string listing matching records plus pre-computed vendor_signals.
    """
    if not merchant_name or not merchant_name.strip():
        return json.dumps({"matches": [], "note": "merchant_name is required"})

    q = merchant_name.strip().lower()
    threshold = settings.fuzzy_match_threshold
    records = _load_ledger()

    matches = []
    for r in records:
        vendor = r.get("vendor", "").lower()
        product = r.get("product", "").lower()
        # Fast path: substring (zero overhead); fall back to fuzzy
        if q in vendor or q in product:
            score = 100.0
        else:
            score = max(_fuzz.partial_ratio(q, vendor), _fuzz.partial_ratio(q, product))
        if settings.fuzzy_debug_logging:
            print(
                f"[fuzzy:ledger_merchant] q={q!r} vendor={r.get('vendor')!r} "
                f"score={score:.1f} included={score >= threshold}"
            )
        if score >= threshold:
            matches.append(
                {k: r[k] for k in ("claim_id", "vendor", "product", "amount_myr", "employee_id", "decision", "recorded_at") if k in r}
            )

    signals = _compute_vendor_signals(matches, employee_id=employee_id)
    return json.dumps({"matches": matches, "count": len(matches), "vendor_signals": signals})


@tool
def search_employee_history(employee_id: str, days_back: int = 90) -> str:
    """Look up the recent claim history for a specific employee.

    Args:
        employee_id: The employee's ID string (e.g. 'E001').
        days_back: How many calendar days to look back (default 90).

    Returns:
        JSON string with the employee's claims in the window plus anomaly_signals
        (z-score spike detection, weekly rate analysis).
    """
    if not employee_id or not employee_id.strip():
        return json.dumps({"matches": [], "note": "employee_id is required"})

    cutoff = datetime.datetime.now(timezone.utc) - timedelta(days=days_back)
    records = _load_ledger()
    employee_records = [r for r in records if r.get("employee_id") == employee_id.strip()]

    recent = []
    for r in employee_records:
        try:
            recorded = datetime.datetime.fromisoformat(r.get("recorded_at", ""))
            if recorded.tzinfo is None:
                recorded = recorded.replace(tzinfo=timezone.utc)
            if recorded >= cutoff:
                recent.append({k: r[k] for k in ("claim_id", "vendor", "product", "amount_myr", "decision", "recorded_at") if k in r})
        except (ValueError, TypeError):
            recent.append({k: r[k] for k in ("claim_id", "vendor", "product", "amount_myr", "decision", "recorded_at") if k in r})

    signals = _compute_spike_signals(recent, days_back)
    return json.dumps({
        "employee_id": employee_id,
        "days_back": days_back,
        "recent_claims": recent,
        "total_in_window": len(recent),
        "all_time_total": len(employee_records),
        "anomaly_signals": signals,
    })


@tool
def lookup_subscription_catalog(merchant_name: str) -> str:
    """Check whether a merchant is a known org-wide SaaS license or approved vendor.

    Uses rapidfuzz partial_ratio matching (threshold from config) on vendor name,
    product name, and aliases.

    Args:
        merchant_name: The vendor or product name to look up.

    Returns:
        JSON string with matched active licenses (including seat counts)
        and approved catalog entries.
    """
    if not merchant_name or not merchant_name.strip():
        return json.dumps({"active_licenses": [], "approved_catalog": [], "note": "merchant_name is required"})

    q = merchant_name.strip().lower()
    threshold = settings.fuzzy_match_threshold
    catalog = _load_catalog()

    matched_licenses = []
    for lic in catalog.get("active_licenses", []):
        vendor = lic.get("vendor", "").lower()
        product = lic.get("product", "").lower()
        aliases = [a.lower() for a in lic.get("aliases", [])]
        if q in vendor or q in product or any(q in a for a in aliases):
            score = 100.0
        else:
            score = max(
                [_fuzz.partial_ratio(q, vendor), _fuzz.partial_ratio(q, product)]
                + [_fuzz.partial_ratio(q, a) for a in aliases]
            )
        if settings.fuzzy_debug_logging:
            print(
                f"[fuzzy:catalog_license] q={q!r} product={lic.get('product')!r} "
                f"score={score:.1f} included={score >= threshold}"
            )
        if score >= threshold:
            matched_licenses.append(lic)

    matched_catalog = []
    for entry in catalog.get("approved_catalog", []):
        product = entry.get("product", "").lower()
        vendor = entry.get("vendor", "").lower()
        if q in product or q in vendor:
            score = 100.0
        else:
            score = max(_fuzz.partial_ratio(q, product), _fuzz.partial_ratio(q, vendor))
        if settings.fuzzy_debug_logging:
            print(
                f"[fuzzy:catalog_entry] q={q!r} product={entry.get('product')!r} "
                f"score={score:.1f} included={score >= threshold}"
            )
        if score >= threshold:
            matched_catalog.append(entry)

    return json.dumps({
        "active_licenses": matched_licenses,
        "approved_catalog_entries": matched_catalog,
        "found_active": len(matched_licenses) > 0,
        "found_in_catalog": len(matched_catalog) > 0,
    })


# ---------------------------------------------------------------------------
# Export all four tools as a list for easy binding
# ---------------------------------------------------------------------------

INTELLIGENCE_TOOLS = [
    search_ledger_by_amount,
    search_ledger_by_merchant,
    search_employee_history,
    lookup_subscription_catalog,
]
