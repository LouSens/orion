"""Intelligence Agent — semantic duplicate detection + fraud investigation.

This is the agent that justifies the "intelligent workflow, not an
automation script" framing. It runs a **real LangChain tool-calling loop**:
the LLM decides which of the four investigative tools to call, in what
order, and whether to call them multiple times based on the accumulating
evidence. The loop is capped at `settings.intelligence_max_iterations`
(default 5) to prevent runaway costs.

The four tools available to the LLM:
    search_ledger_by_amount      – finds past claims near the same MYR value
    search_ledger_by_merchant    – finds past claims for the same vendor
    search_employee_history      – checks recent claim volume for the employee
    lookup_subscription_catalog  – flags known SaaS that should go through procurement

At the end of the loop (either LLM stops or cap reached), the accumulated
tool results and conversation are fed back to the LLM for a final
IntelligenceReport in structured JSON.

Output: IntelligenceReport whose `recommendation` field directly
influences Supervisor routing.
"""
from __future__ import annotations

import json

from langsmith import traceable

from ..config import settings
from ..llm import LLMError, chat, chat_structured
from ..schemas import IntelligenceReport
from ..state import WorkflowState
from ..tools import SubscriptionCatalog
from ..tools.ledger_search import INTELLIGENCE_TOOLS

_catalog = SubscriptionCatalog()

# ---------------------------------------------------------------------------
# Tool registry — name → callable(args_dict) → str
# ---------------------------------------------------------------------------

_TOOL_MAP: dict[str, object] = {t.name: t for t in INTELLIGENCE_TOOLS}


def _invoke_tool(name: str, args: dict) -> str:
    """Look up and call a tool by name; return its string output."""
    tool = _TOOL_MAP.get(name)
    if tool is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return tool.invoke(args)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Tool schema block for injection into the system prompt
# ---------------------------------------------------------------------------

def _tools_schema_block() -> str:
    lines = ["You have access to the following tools (call them by name with JSON args):\n"]
    for t in INTELLIGENCE_TOOLS:
        lines.append(f"  {t.name}: {t.description}")
    lines.append(
        "\nTo call a tool, output ONLY a JSON object in this exact format:\n"
        '  {"tool_call": {"name": "<tool_name>", "args": {<args>}}}\n'
        "When you are done investigating and ready to produce the final report, output:\n"
        '  {"done": true}'
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SYSTEM_INVESTIGATOR = f"""You are the Intelligence Agent in an expense-reimbursement workflow.
Your mission: investigate whether a subscription reimbursement request is a
duplicate of an existing org license, and whether better alternatives exist.

{_tools_schema_block()}

Judgement criteria:
- "Likely duplicate" means the requested product is substantively the same
  software as an existing org licence — same vendor family, same core
  capability — even if the marketing names differ.
- If a duplicate exists AND the existing licence has available seats →
  recommend "block_duplicate".
- If a duplicate exists but NO seats are available → recommend
  "suggest_alternative".
- If the product is reasonable and no duplicate → recommend "proceed".

Think step-by-step. Call tools to gather evidence. Stop when you have
enough — or when you have exhausted what the tools can tell you.
"""

SYSTEM_REPORTER = """You are the Intelligence Agent. Based on the investigation
conversation provided, produce the final structured IntelligenceReport.
Do NOT call any more tools — synthesise what you found into the report.

IMPORTANT: The tools have already pre-calculated all statistical signals
(anomaly_signals, duplicate_signals, vendor_signals). Your job is to NARRATE
these signals in plain language, not recalculate them. Use the signal fields
directly in your reasoning and rationale."""


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

@traceable(run_type="chain", name="agent.intelligence")
def intelligence_node(state: WorkflowState) -> WorkflowState:
    claim = state["intake"]
    submission = state["submission"]
    max_iter = settings.intelligence_max_iterations

    # Seed the conversation with the claim context.
    initial_user_msg = f"""Employee: {submission.employee_name} ({submission.employee_id}), team: {submission.employee_team}
Employee ID for tool calls: {submission.employee_id}

Extracted claim:
- vendor: {claim.vendor}
- product: {claim.product}
- category: {claim.category}
- amount_myr: {claim.amount_myr}
- billing_period: {claim.billing_period}
- justification: {claim.business_justification}
- missing_fields: {claim.missing_fields}

{_catalog.as_prompt_block()}

IMPORTANT: When calling search_ledger_by_merchant or search_ledger_by_amount,
always pass employee_id="{submission.employee_id}" so vendor_signals and
duplicate_signals are computed correctly for this employee.

Begin your investigation. Call tools to gather evidence, then signal done."""

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_INVESTIGATOR},
        {"role": "user", "content": initial_user_msg},
    ]

    degraded = False
    iterations = 0

    # -----------------------------------------------------------------------
    # Tool-calling loop
    # -----------------------------------------------------------------------
    while iterations < max_iter:
        raw = chat(
            messages,
            temperature=settings.cfg_intelligence.temperature,
            max_tokens=settings.cfg_intelligence.max_tokens,
            response_format_json=True,
        )
        messages.append({"role": "assistant", "content": raw})
        iterations += 1

        # Parse the LLM's intent.
        try:
            intent = json.loads(raw)
        except json.JSONDecodeError:
            # LLM produced free text — treat as "done".
            break

        if intent.get("done"):
            break

        tool_call = intent.get("tool_call")
        if not tool_call or "name" not in tool_call:
            # No recognisable structure — stop.
            break

        tool_name = tool_call["name"]
        tool_args = tool_call.get("args", {})
        result = _invoke_tool(tool_name, tool_args)

        messages.append({
            "role": "user",
            "content": f"Tool `{tool_name}` result:\n{result}\n\nContinue investigating or signal done.",
        })
    else:
        # Loop exhausted without a "done" signal.
        degraded = True

    # -----------------------------------------------------------------------
    # Structured report extraction
    # -----------------------------------------------------------------------
    messages.append({
        "role": "user",
        "content": (
            "The investigation loop has ended"
            + (" (iteration cap reached — mark this as a degraded report)" if degraded else "")
            + ". Now produce the final IntelligenceReport JSON."
        ),
    })
    # Swap system prompt to reporter mode for the final call.
    report_messages = [{"role": "system", "content": SYSTEM_REPORTER}] + messages[1:]

    report = chat_structured(
        report_messages,
        IntelligenceReport,
        cfg=settings.cfg_intelligence,
    )

    return {"intelligence": report, "trace": [f"intelligence(iters={iterations})"]}
