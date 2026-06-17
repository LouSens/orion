"""Security middleware for Orion.

Provides:
  - API key authentication (X-API-Key header or ?api_key= query param)
  - Per-IP sliding-window rate limiting (no external dependency)
  - Input sanitisation helpers (prompt-injection scrubbing, field length caps)

Usage in main.py:
    from .security import RateLimitMiddleware, api_key_dependency, sanitise_submission
    app.add_middleware(RateLimitMiddleware)
    # then use Depends(api_key_dependency) on protected routes
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery

from .config import settings
from .schemas import ReimbursementSubmission

# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_API_KEY_QUERY = APIKeyQuery(name="api_key", auto_error=False)

# Acceptable demo keys when the env var is not set / is the placeholder.
_DEMO_KEYS: frozenset[str] = frozenset({"dev-key", "demo"})


def _resolve_configured_keys() -> frozenset[str]:
    """Return the set of valid API keys from settings.

    Supports a comma-separated list in ``settings.orion_api_keys`` so that
    key rotation is possible without downtime.
    """
    raw = getattr(settings, "orion_api_keys", "")
    keys: set[str] = set()
    for k in raw.split(","):
        k = k.strip()
        if k:
            keys.add(k)
    if not keys:
        # Fall back to demo keys so the app starts without configuration.
        return _DEMO_KEYS
    return frozenset(keys)


def _is_valid_key(key: str | None) -> bool:
    if not key:
        return False
    return key in _resolve_configured_keys()


async def api_key_dependency(
    header_key: Optional[str] = Security(_API_KEY_HEADER),
    query_key: Optional[str] = Security(_API_KEY_QUERY),
) -> str:
    """FastAPI dependency: validates the API key from header or query string.

    Raises HTTP 401 when no key is supplied and HTTP 403 when the key is invalid.
    Returns the validated key on success.
    """
    key = header_key or query_key
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Supply X-API-Key header or ?api_key= query parameter.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if not _is_valid_key(key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )
    return key


# ---------------------------------------------------------------------------
# Rate Limiting  (sliding-window, in-memory, thread-safe)
# ---------------------------------------------------------------------------

_RATE_WINDOWS: dict[str, deque[float]] = defaultdict(deque)
_RATE_LOCK = Lock()

# Default limits — override via settings if desired.
_LIMIT_SUBMIT = 10       # max requests to /api/submit per IP per window
_LIMIT_GENERAL = 120     # max requests to all other API routes per IP per window
_WINDOW_SECONDS = 60     # sliding window duration


def _client_ip(request: Request) -> str:
    """Extract the real client IP, honouring X-Forwarded-For if present."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate(key: str, limit: int, window: float = _WINDOW_SECONDS) -> None:
    """Sliding-window rate check.  Raises HTTP 429 if limit exceeded."""
    now = time.monotonic()
    cutoff = now - window
    with _RATE_LOCK:
        dq = _RATE_WINDOWS[key]
        # Evict timestamps outside the window.
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: max {limit} requests per {int(window)}s window.",
                headers={"Retry-After": str(int(window))},
            )
        dq.append(now)


class RateLimitMiddleware:
    """ASGI middleware that applies per-IP rate limits before request handling.

    - /api/submit  → LIMIT_SUBMIT   (10 req/60 s) — expensive workflow calls
    - /api/*       → LIMIT_GENERAL  (120 req/60 s)
    - /assets/*    → unrestricted   (static files)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = scope.get("path", "")

        if path.startswith("/api/"):
            ip = _client_ip(request)
            limit = _LIMIT_SUBMIT if path == "/api/submit" else _LIMIT_GENERAL
            try:
                _check_rate(f"{ip}:{path}", limit)
            except HTTPException as exc:
                from fastapi.responses import JSONResponse
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=dict(exc.headers or {}),
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Input Sanitisation
# ---------------------------------------------------------------------------

# Known prompt-injection trigger phrases (case-insensitive).
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"disregard\s+(all\s+)?previous", re.I),
    re.compile(r"forget\s+(all\s+)?previous", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a\s+)?(?:an?\s+)?(?:different|new|evil|DAN)", re.I),
    re.compile(r"act\s+as\s+(?:if\s+you\s+are\s+)?(?:a\s+)?(?:DAN|jailbroken|uncensored)", re.I),
    re.compile(r"\bDAN\b"),  # "Do Anything Now" jailbreak keyword
    re.compile(r"prompt\s+injection", re.I),
    re.compile(r"reveal\s+(?:your\s+)?(?:system\s+)?prompt", re.I),
    re.compile(r"system\s+prompt\s*:", re.I),
    re.compile(r"<\s*/?(?:system|user|assistant)\s*>", re.I),  # XML role tags
]

# Field length caps (characters).
_MAX_LENGTHS: dict[str, int] = {
    "employee_id":   50,
    "employee_name": 120,
    "employee_team": 120,
    "free_text":     4000,
    "receipt_text":  20000,
}


def _check_injection(value: str, field: str) -> None:
    """Raise HTTP 422 if ``value`` contains a prompt-injection pattern."""
    for pat in _INJECTION_PATTERNS:
        if pat.search(value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Field '{field}' contains disallowed content.",
            )


def _truncate(value: str, field: str) -> str:
    """Silently truncate a field value that exceeds its length cap."""
    cap = _MAX_LENGTHS.get(field)
    if cap and len(value) > cap:
        return value[:cap]
    return value


def sanitise_submission(payload: ReimbursementSubmission) -> ReimbursementSubmission:
    """Validate and sanitise a ``ReimbursementSubmission`` before it enters the
    workflow.

    1. Checks every string field for prompt-injection patterns.
    2. Truncates fields that exceed their length caps.
    3. Returns a new ``ReimbursementSubmission`` (the original is not mutated).

    Raises ``HTTPException(422)`` if injection is detected.
    """
    text_fields: dict[str, str | None] = {
        "employee_id":   payload.employee_id,
        "employee_name": payload.employee_name,
        "employee_team": payload.employee_team,
        "free_text":     payload.free_text,
        "receipt_text":  payload.receipt_text,
    }

    cleaned: dict[str, str | None] = {}
    for field, value in text_fields.items():
        if value is None:
            cleaned[field] = None
            continue
        _check_injection(value, field)
        cleaned[field] = _truncate(value, field)

    return payload.model_copy(update={k: v for k, v in cleaned.items() if v is not None})
