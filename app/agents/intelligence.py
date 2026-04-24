"""Intelligence Agent — semantic duplicate detection + alternatives.

This is the agent that justifies the "intelligent workflow, not an
automation script" framing. It does three things that are hard without an
LLM:

1. **Duplicate detection via semantic similarity.** "ChatGPT Plus",
   "OpenAI GPT-4 subscription", and "ChatGPT Team" look different as
   strings but map to the same org license. We fuzzy-prefilter then hand
   the final call to the LLM with full organisational context.
2. **Alternative suggestion.** If the org already has seats available on
   a comparable license, recommend that instead.
3. **Cross-reference against the approved catalog.** Flag self-purchases
   of tools that should go through a team-managed account.

The output is a structured `IntelligenceReport` whose `recommendation`
field directly influences downstream routing.
"""
from __future__ import annotations

from langsmith import traceable

from ..config import settings
from ..llm import chat_structured
from ..schemas import IntelligenceReport
from ..state import WorkflowState
from ..tools import SubscriptionCatalog

_catalog = SubscriptionCatalog()

SYSTEM = """You are the Intelligence Agent. You reason about whether a
reimbursement request overlaps with software the organisation already
licenses, and whether a better alternative exists.

You have access to:
1. The employee's extracted claim.
2. The list of all active organisation-wide SaaS licences (with seat
   availability, owner team, and aliases).
3. A curated catalog of approved vendors.
4. A pre-filtered shortlist of licences that fuzzy-match the request.

Your judgement criteria:
- "Likely duplicate" means the requested product is substantively the
  same software as an existing org licence — same vendor family, same
  core capability — even if the marketing names differ (e.g. "Copilot"
  vs "GitHub Copilot Business" under "GitHub Enterprise"). Consider the
  employee's team when deciding (a designer asking for Figma when the
  Design team owns Figma Org is almost always a duplicate).
- If a duplicate exists AND the existing licence has available seats,
  recommend "block_duplicate" and name the licence + owner team.
- If a duplicate exists but NO seats are available, recommend
  "suggest_alternative" — suggest either a cheaper tier or requesting a
  seat expansion rather than a new subscription.
- If the product is reasonable and no duplicate, recommend "proceed".
- `similarity_score` is your confidence that two products are truly the
  same underlying software (0..1). Use the alias list.

Be strict but fair. A duplicate finding blocks the claim, so only call
it when you genuinely believe the org already pays for this capability.
"""


@traceable(run_type="chain", name="agent.intelligence")
def intelligence_node(state: WorkflowState) -> WorkflowState:
    claim = state["intake"]
    submission = state["submission"]

    fuzzy_query = " ".join(filter(None, [claim.product, claim.vendor]))
    candidates = _catalog.fuzzy_candidates(fuzzy_query) if fuzzy_query else []

    user_msg = f"""Employee team: {submission.employee_team}

Extracted claim:
- vendor: {claim.vendor}
- product: {claim.product}
- category: {claim.category}
- amount_myr: {claim.amount_myr}
- billing_period: {claim.billing_period}
- justification: {claim.business_justification}

{_catalog.as_prompt_block()}

Fuzzy-matched shortlist (pre-filter only — make your own decision):
{[c['id'] + ': ' + c['product'] for c in candidates] or 'none'}

Produce the intelligence report."""

    report = chat_structured(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        IntelligenceReport,
        cfg=settings.cfg_intelligence,
    )

    trace = state.get("trace", []) + ["intelligence"]
    return {**state, "intelligence": report, "trace": trace}
