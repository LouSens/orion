"""Org subscription ledger + approved-vendor catalog.

Used by the Intelligence agent for:
  - duplicate detection (is a team already paying for this?)
  - alternative suggestion (is there a seat on an existing org license?)
  - cross-reference (is this product on the approved catalog at all?)

Fuzzy pre-filter (rapidfuzz) narrows the candidate set; the final
semantic judgement is delegated to the LLM — which is the whole point of
using GLM-5.1 here, not a hard-coded string match.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from ..config import settings


class SubscriptionCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.data_dir / "org_subscriptions.json")

    @lru_cache(maxsize=1)
    def _load(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def active_licenses(self) -> list[dict[str, Any]]:
        return self._load()["active_licenses"]

    def approved_catalog(self) -> list[dict[str, Any]]:
        return self._load()["approved_catalog"]

    def fuzzy_candidates(self, query: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        """Return licences whose name/vendor/alias fuzzy-matches `query`.

        Cheap first-pass filter; the agent's LLM makes the final call on
        whether any of these are truly the same product.
        """
        q = (query or "").lower().strip()
        if not q:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for lic in self.active_licenses():
            haystacks = [lic["product"], lic["vendor"], *lic.get("aliases", [])]
            best = max(fuzz.partial_ratio(q, h.lower()) for h in haystacks)
            if best >= 55:
                scored.append((best, lic))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [lic for _, lic in scored[:top_k]]

    def as_prompt_block(self) -> str:
        lics = self.active_licenses()
        cat = self.approved_catalog()
        lines = ["Organisation-wide active SaaS licences:"]
        for l in lics:
            lines.append(
                f"- {l['id']}: {l['product']} ({l['vendor']}), owner={l['owner_team']}, "
                f"seats={l['seats_used']}/{l['seats_total']} used "
                f"(available={l['seats_available']}), aliases={l.get('aliases', [])}"
            )
        lines.append("")
        lines.append("Approved vendor catalog:")
        for c in cat:
            lines.append(f"- {c['product']} [{c['category']}]: {c['note']}")
        return "\n".join(lines)
