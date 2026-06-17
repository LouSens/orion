"""Deterministic currency token extractor.

Called by Intake before the LLM processes the receipt, providing a ground-truth
amount anchor that reduces hallucination risk.
"""
import re
from typing import Optional

# Matches: RM 48.50, MYR48.50, $485.00, €1,200.00, 250.00
_CURRENCY_RE = re.compile(
    r'(?:RM|MYR|USD|SGD|\$|€|£|¥)?\s*(\d{1,6}(?:[,\.]\d{2,3})?)',
    re.IGNORECASE,
)


def extract_largest_amount(text: str) -> Optional[float]:
    """Return the largest numeric currency token found in text, or None."""
    if not text:
        return None

    candidates = []
    for match in _CURRENCY_RE.finditer(text):
        raw = match.group(1).replace(',', '.')
        try:
            val = float(raw)
            # Filter noise: amounts < 0.50 or > 1,000,000 are almost certainly not prices
            if 0.50 <= val <= 1_000_000:
                candidates.append(val)
        except ValueError:
            pass

    return max(candidates) if candidates else None


def amount_discrepancy_flag(
    regex_amount: Optional[float],
    claimed_amount: Optional[float],
    threshold_pct: float = 20.0,
) -> bool:
    """Return True if regex_amount and claimed_amount diverge by more than threshold_pct%."""
    if regex_amount is None or claimed_amount is None or claimed_amount == 0:
        return False
    pct_diff = abs(regex_amount - claimed_amount) / claimed_amount * 100
    return pct_diff > threshold_pct
