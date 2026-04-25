"""Synthetic claim generator for nightly soak.

Produces N perturbed `ReimbursementSubmission` payloads by varying vendor
casing, currency, and amount around the policy thresholds. Output is
JSONL on stdout (or a file with --out) so the nightly CI job can pipe it
into the live workflow and aggregate pass/fail without committing the
generated payloads.

Usage:
    python -m scripts.gen_claims --count 50 --seed 42
    python -m scripts.gen_claims --count 20 --out tmp/synth.jsonl
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
from pathlib import Path
from typing import Iterator

from app.schemas import ReimbursementSubmission

# Deliberately small set: synthetics are for *threshold-edge* coverage,
# not creative diversity.
VENDORS = [
    ("Notion Labs Inc.", "Notion Plus", "productivity"),
    ("Figma Inc.", "Figma Pro", "design"),
    ("OpenAI", "ChatGPT Plus", "ai_tools"),
    ("Anthropic", "Claude Pro", "ai_tools"),
    ("Datadog Inc.", "Datadog Pro", "engineering"),
]

CASINGS = [str.lower, str.upper, str.title, lambda s: s]
CURRENCIES = [
    ("MYR", lambda v: v),
    ("RM", lambda v: v),
    ("USD", lambda v: round(v / 4.7, 2)),
]


def _amount_around(threshold: float, jitter_pct: float = 5.0) -> float:
    """Pick an amount within ±jitter_pct% of `threshold`."""
    lo = threshold * (1 - jitter_pct / 100)
    hi = threshold * (1 + jitter_pct / 100)
    return round(random.uniform(lo, hi), 2)


def generate(count: int) -> Iterator[ReimbursementSubmission]:
    threshold_cycle = itertools.cycle([100, 500, 5000, 7800])
    for i in range(count):
        vendor, product, category = random.choice(VENDORS)
        casing = random.choice(CASINGS)
        cur_code, cur_fn = random.choice(CURRENCIES)
        amount_myr = _amount_around(next(threshold_cycle))
        receipt_amount = cur_fn(amount_myr)
        # Craft both fields with the chosen casing variation.
        vendor_str = casing(vendor)
        product_str = casing(product)
        yield ReimbursementSubmission(
            employee_id=f"EMP-{1000 + i}",
            employee_name=f"Synthetic User {i}",
            employee_team=random.choice(["Engineering", "Design", "Operations", "Marketing"]),
            free_text=(
                f"Reimburse {product_str} for {category} use, "
                f"about {cur_code} {receipt_amount} this cycle."
            ),
            receipt_text=(
                f"{vendor_str} — {product_str} — {cur_code} {receipt_amount:.2f} — "
                "2026-04-25"
            ),
        )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, default=None,
                   help="write JSONL here instead of stdout")
    args = p.parse_args()

    random.seed(args.seed)
    lines = (json.dumps(s.model_dump(mode="json")) for s in generate(args.count))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {args.count} synthetic claims to {args.out}")
    else:
        for line in lines:
            print(line)


if __name__ == "__main__":
    main()
