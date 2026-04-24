"""Policy retrieval. Loads the JSON rulebook and exposes simple queries."""
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
    def _load(self) -> list[dict[str, Any]]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data["policies"]

    def all(self) -> list[dict[str, Any]]:
        return self._load()

    def applicable(self, amount_myr: float | None) -> list[dict[str, Any]]:
        # At MVP scope, all policies are always candidate-applicable; filtering
        # is the LLM's job. We still attach the rulebook verbatim.
        return self._load()

    def as_prompt_block(self) -> str:
        rules = self._load()
        lines = ["Company reimbursement policy:"]
        for r in rules:
            lines.append(f"- [{r['rule_id']} / {r['severity']}] {r['title']}: {r['description']}")
        return "\n".join(lines)
