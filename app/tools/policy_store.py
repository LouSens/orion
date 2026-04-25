"""Policy retrieval. Loads the JSON rulebook and exposes simple queries.

policies.json is structured as two top-level sections:
  hard_policies — block-severity rules (automatic or llm_evaluated enforcement)
  soft_policies — warn-severity rules (routing hints and preferences)

Section membership encodes severity, so no per-entry severity field is needed.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import settings


class PolicyStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.data_dir / "policies.json")

    @lru_cache(maxsize=1)
    def _load(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def hard_rules(self) -> list[dict]:
        return self._load()["hard_policies"]

    def soft_rules(self) -> list[dict]:
        return self._load()["soft_policies"]

    def all(self) -> list[dict]:
        return self.hard_rules() + self.soft_rules()

    def by_rule_id(self, rule_id: str) -> dict | None:
        return next((r for r in self.all() if r["rule_id"] == rule_id), None)

    def severity_for(self, rule_id: str) -> str:
        """Return 'block' if the rule is in hard_policies, 'warn' otherwise."""
        if any(r["rule_id"] == rule_id for r in self.hard_rules()):
            return "block"
        return "warn"

    def automatic_rule_ids(self) -> list[str]:
        """IDs of rules with enforcement=='automatic', hard rules first."""
        return [r["rule_id"] for r in self.all() if r.get("enforcement") == "automatic"]

    def as_prompt_block(self) -> str:
        lines = ["Company reimbursement policy:"]
        lines.append("  Hard rules (blocking violations):")
        for r in self.hard_rules():
            tag = "AUTO" if r.get("enforcement") == "automatic" else "LLM"
            lines.append(f"  - [{r['rule_id']} / {tag}] {r['title']}: {r['description']}")
        lines.append("  Soft rules (routing guidance):")
        for r in self.soft_rules():
            lines.append(f"  - [{r['rule_id']} / AUTO] {r['title']}: {r['description']}")
        return "\n".join(lines)
