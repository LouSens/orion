"""ILMU (YTL Labs) GLM-5.1 client.

Thin wrapper over the OpenAI-compatible Chat Completions API exposed by
ILMU. Every agent talks to `chat()` / `chat_structured()`; only this
module changes if the deployment shape does.

Resilience:
  - Transient failures (timeouts, connection errors, 408/425/429/5xx) are
    retried with exponential backoff up to `settings.ilmu_max_retries`.
  - Structured output retries once on schema-validation failure with the
    validator error fed back to the model as a correction prompt.
  - `response_format={"type":"json_object"}` is sent when
    `ilmu_supports_json_mode=True`. If the server rejects it (400 with
    "response_format" in the error), we auto-fall-back for the process.

LangSmith tracing: every call is wrapped with `@traceable` so each agent
step shows up in the run tree with inputs/outputs.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Type, TypeVar

from langsmith import traceable
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from .config import AgentLLMConfig, settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


_client: OpenAI | None = None
# Process-wide flag that flips off if the server refuses json_object mode.
_json_mode_enabled: bool = True
# Process-wide flag: some models (o-series, newer deployments) require
# max_completion_tokens instead of max_tokens. Flips on first rejection.
_use_max_completion_tokens: bool = False


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=settings.ilmu_base_url,
            api_key=settings.ilmu_api_key,
            timeout=settings.ilmu_timeout_seconds,
            max_retries=0,  # we do our own backoff so tracing sees each attempt
        )
    return _client


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in (408, 425, 429, 500, 502, 503, 504)
    return False


def _json_mode_rejected(exc: Exception) -> bool:
    if isinstance(exc, APIStatusError) and exc.status_code == 400:
        msg = str(exc).lower()
        return "response_format" in msg or "json_object" in msg
    return False


def _max_tokens_rejected(exc: Exception) -> bool:
    """Return True if the server wants max_completion_tokens instead of max_tokens."""
    if isinstance(exc, APIStatusError) and exc.status_code == 400:
        msg = str(exc).lower()
        return "max_tokens" in msg and "max_completion_tokens" in msg
    return False


@traceable(run_type="llm", name="ilmu.chat")
def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.1,
    max_tokens: int = 1200,
    response_format_json: bool | None = None,
) -> str:
    """Call ILMU chat completions. Returns raw assistant text."""
    global _json_mode_enabled

    use_json = (
        response_format_json
        if response_format_json is not None
        else (settings.ilmu_supports_json_mode and _json_mode_enabled)
    )

    def _call(with_json: bool) -> str:
        tokens_key = "max_completion_tokens" if _use_max_completion_tokens else "max_tokens"
        kwargs: dict[str, Any] = {
            "model": settings.ilmu_model,
            "messages": messages,
            "temperature": temperature,
            tokens_key: max_tokens,
        }
        if with_json:
            kwargs["response_format"] = {"type": "json_object"}
        resp = _get_client().chat.completions.create(**kwargs)
        # `resp` is a pydantic-like object (ChatCompletion), NOT a dict.
        try:
            return resp.choices[0].message.content or ""
        except (AttributeError, IndexError) as ex:
            raise LLMError(f"Unexpected ILMU response shape: {resp}") from ex

    last_exc: Exception | None = None
    for attempt in range(settings.ilmu_max_retries + 1):
        try:
            return _call(use_json)
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if use_json and _json_mode_rejected(e):
                _json_mode_enabled = False
                use_json = False
                continue  # retry immediately without json_object
            if _max_tokens_rejected(e):
                global _use_max_completion_tokens
                _use_max_completion_tokens = True
                continue  # retry immediately with max_completion_tokens
            if attempt < settings.ilmu_max_retries and _is_transient(e):
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise LLMError(f"ILMU request failed after {attempt + 1} attempt(s): {e}") from e

    raise LLMError(f"ILMU request exhausted retries: {last_exc}")


_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# Keys to drop from json_schema to cut prompt bloat. GLM-5.1 doesn't need
# titles/descriptions/defaults — field names + types are enough.
_SCHEMA_NOISE_KEYS = {"title", "description", "default", "examples"}


def _compact_schema(node: Any) -> Any:
    """Recursively strip human-facing / optional keys from a JSON schema.
    Cuts token count by ~60% on typical pydantic output without losing
    structural info the model needs to emit valid JSON."""
    if isinstance(node, dict):
        return {
            k: _compact_schema(v)
            for k, v in node.items()
            if k not in _SCHEMA_NOISE_KEYS
        }
    if isinstance(node, list):
        return [_compact_schema(v) for v in node]
    return node


def _extract_json(raw: str) -> dict[str, Any]:
    cleaned = _FENCE.sub("", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(cleaned)
        if not m:
            raise LLMError(f"No JSON object found in LLM output: {raw[:200]}")
        return json.loads(m.group(0))


@traceable(run_type="llm", name="ilmu.chat_structured")
def chat_structured(
    messages: list[dict[str, str]],
    schema: Type[T],
    *,
    temperature: float = 0.1,
    max_tokens: int = 1200,
    max_retries: int = 1,
    cfg: AgentLLMConfig | None = None,
) -> T:
    """Ask the LLM for JSON matching `schema`. Retries once on parse/validation
    error, feeding the validator message back to the model."""
    if cfg is not None:
        temperature = cfg.temperature
        max_tokens = cfg.max_tokens

    compact = _compact_schema(schema.model_json_schema())
    sys_injection = (
        "You MUST respond with a single JSON object that validates against "
        "this JSON schema:\n"
        f"{json.dumps(compact, separators=(',', ':'))}\n"
        "Return JSON only — no prose, no markdown fences."
    )
    merged = list(messages)
    if merged and merged[0]["role"] == "system":
        merged[0] = {"role": "system", "content": merged[0]["content"] + "\n\n" + sys_injection}
    else:
        merged.insert(0, {"role": "system", "content": sys_injection})

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        raw = chat(merged, temperature=temperature, max_tokens=max_tokens)
        try:
            obj = _extract_json(raw)
            return schema.model_validate(obj)
        except (LLMError, ValidationError, json.JSONDecodeError) as e:
            last_err = e
            merged.append({"role": "assistant", "content": raw})
            merged.append({
                "role": "user",
                "content": f"Your last response failed validation: {e}. "
                           "Return a corrected JSON object only.",
            })
    raise LLMError(f"Structured output failed after {max_retries + 1} attempts: {last_err}")
