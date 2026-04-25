"""JSON-file ledger. Intentionally boring — swap for Postgres later."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from ..config import settings


class Ledger:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.data_dir / "ledger.json")
        self._lock = threading.Lock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"records": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def append(self, record: dict[str, Any]) -> None:
        with self._lock:
            data = self._read()
            data["records"].append(record)
            self._write(data)

    def all(self) -> list[dict[str, Any]]:
        return self._read()["records"]

    def by_employee(self, employee_id: str) -> list[dict[str, Any]]:
        return [r for r in self.all() if r.get("employee_id") == employee_id]

    def delete(self, claim_id: str) -> bool:
        with self._lock:
            data = self._read()
            original_len = len(data["records"])
            data["records"] = [r for r in data["records"] if r.get("claim_id") != claim_id]
            if len(data["records"]) < original_len:
                self._write(data)
                return True
            return False

    def clear(self, employee_id: str | None = None) -> int:
        with self._lock:
            data = self._read()
            if employee_id:
                original = data["records"]
                data["records"] = [r for r in original if r.get("employee_id") != employee_id]
                removed = len(original) - len(data["records"])
            else:
                removed = len(data["records"])
                data["records"] = []
            self._write(data)
            return removed
