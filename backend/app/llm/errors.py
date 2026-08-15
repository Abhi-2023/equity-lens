"""Error classification for the LLM gateway's fallback routing.

Groq's Python SDK (which langchain-groq calls under the hood) uses the same
exception hierarchy shape as the OpenAI SDK — a `GroqError` base with
`APIStatusError` subclasses per HTTP status family. langchain-groq lets these
propagate as-is from `.ainvoke()`, so we classify on the SDK's own exception
types rather than parsing status codes ourselves.
"""
from __future__ import annotations

import enum
import re

import groq


class ErrorClass(enum.Enum):
    RATE_LIMIT = "rate_limit"  # exhausted for this (account, model) — skip + cooldown
    AUTH = "auth"  # bad key — skip the rest of this account entirely, no cooldown needed
    CONTEXT_LENGTH = "context_length"  # prompt too big for this model — try a different model
    TRANSIENT = "transient"  # timeout/connection/5xx — worth one retry before falling back
    UNKNOWN = "unknown"  # anything else — treat like TRANSIENT but log loudly


_RETRY_AFTER_RE = re.compile(
    r"try again in (?:(?P<minutes>\d+)m)?(?P<seconds>\d+(?:\.\d+)?)s", re.IGNORECASE
)


def classify_error(exc: Exception) -> ErrorClass:
    if isinstance(exc, groq.RateLimitError):
        return ErrorClass.RATE_LIMIT
    if isinstance(exc, groq.AuthenticationError):
        return ErrorClass.AUTH
    if isinstance(exc, groq.BadRequestError) and "context" in str(exc).lower():
        return ErrorClass.CONTEXT_LENGTH
    if isinstance(exc, (groq.APITimeoutError, groq.APIConnectionError, groq.InternalServerError)):
        return ErrorClass.TRANSIENT
    return ErrorClass.UNKNOWN


def parse_retry_after_seconds(exc: Exception) -> float | None:
    """Groq embeds a human-readable retry-after in the error message itself,
    e.g. "Please try again in 19m41.088s". Falls back to None (caller uses a
    default cooldown) if the message doesn't match — the format isn't a
    documented contract, just observed behavior."""
    match = _RETRY_AFTER_RE.search(str(exc))
    if not match:
        return None
    minutes = int(match.group("minutes") or 0)
    seconds = float(match.group("seconds"))
    return minutes * 60 + seconds
