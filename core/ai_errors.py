"""Common error classification for AI providers and engines."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorKind(str, Enum):
    AUTHENTICATION = "authentication"
    QUOTA_EXHAUSTED = "quota_exhausted"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    UNAVAILABLE = "unavailable"
    MODEL_NOT_FOUND = "model_not_found"
    INVALID_CONFIGURATION = "invalid_configuration"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ErrorInfo:
    kind: ErrorKind
    recoverable: bool
    user_action_required: bool
    message: str
    provider: str = ""
    model: str = ""
    partial: bool = False


_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;]+)"),
)


def redact_credentials(value: Any, *secrets: str) -> str:
    """Return a log-safe message without credentials or bearer tokens."""
    text = str(value or "")
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(
            lambda match: f"{match.group(1)}=[REDACTED]",
            text,
        )
    return text


def classify_error(
    error: BaseException | str,
    *,
    provider: str = "",
    model: str = "",
    partial: bool = False,
) -> ErrorInfo:
    """Classify an external AI failure for future routing decisions."""
    text = redact_credentials(error)
    low = text.lower()

    if any(token in low for token in ("401", "403", "api key", "unauthorized",
                                      "authentication", "invalid api key")):
        kind = ErrorKind.AUTHENTICATION
    elif "429" in low or "resource_exhausted" in low:
        kind = ErrorKind.QUOTA_EXHAUSTED if any(
            token in low for token in ("quota", "resource_exhausted", "daily")
        ) else ErrorKind.RATE_LIMITED
    elif any(token in low for token in ("timeout", "timed out", "deadline_exceeded")):
        kind = ErrorKind.TIMEOUT
    elif any(token in low for token in ("connection refused", "connecterror",
                                        "connection reset",
                                        "all connection attempts failed",
                                        "getaddrinfo", "network is unreachable")):
        kind = ErrorKind.CONNECTION
    elif any(token in low for token in ("503", "504", "service unavailable",
                                        "temporarily unavailable", "overloaded")):
        kind = ErrorKind.UNAVAILABLE
    elif any(token in low for token in ("404", "not found", "unknown model",
                                        "model does not exist")):
        kind = ErrorKind.MODEL_NOT_FOUND
    elif any(token in low for token in ("invalid configuration", "not configured",
                                        "no model", "no address", "missing",
                                        "not approved", "policy blocked",
                                        "restricted to")):
        kind = ErrorKind.INVALID_CONFIGURATION
    elif any(token in low for token in ("invalid response", "malformed",
                                        "invalid json", "empty answer",
                                        "unexpected response")):
        kind = ErrorKind.INVALID_RESPONSE
    else:
        kind = ErrorKind.UNKNOWN

    recoverable = kind in {
        ErrorKind.QUOTA_EXHAUSTED,
        ErrorKind.RATE_LIMITED,
        ErrorKind.TIMEOUT,
        ErrorKind.CONNECTION,
        ErrorKind.UNAVAILABLE,
    }
    return ErrorInfo(
        kind=kind,
        recoverable=recoverable and not partial,
        user_action_required=kind in {
            ErrorKind.AUTHENTICATION,
            ErrorKind.MODEL_NOT_FOUND,
            ErrorKind.INVALID_CONFIGURATION,
        },
        message=text,
        provider=provider,
        model=model,
        partial=partial,
    )
