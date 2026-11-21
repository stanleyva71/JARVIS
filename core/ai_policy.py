"""Safe-by-default policy for external AI requests."""
from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
import re
from urllib.parse import urlparse


class PolicyViolation(ValueError):
    """Raised before a request when its provider or model is not approved."""


@dataclass(frozen=True)
class PolicyDecision:
    provider: str
    model: str
    local: bool
    free_only: bool


_GEMINI_LIVE_MODELS = {
    "models/gemini-3.8-live",
    "models/gemini-3.1-flash-live-preview",
    "models/gemini-2.5-flash-native-audio-preview-12-2025",
}

_GEMINI_TEXT_MODELS = {
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-3-flash-preview",
}

# These are the public free-tier models currently used by the project. A model
# not listed here is blocked instead of being assumed free.
_GROQ_FREE_MODELS = {
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3-32b",
}

# Account-scoped Workers AI models that are known to work in the OpenAI-compatible
# chat API and do not require a separate paid model purchase. This is deliberately
# conservative: unknown/new Workers AI models stay blocked by default.
_CLOUDFLARE_FREE_CHAT_MODELS = {
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "@cf/qwen/qwen2.5-coder-32b-instruct",
}

_CLOUDFLARE_ACCOUNT_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _host_is_local(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
        if host == "localhost" or host == "::1":
            return True
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _is_official_https(url: str, hostname: str, path: str) -> bool:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() == hostname
        and port in (None, 443)
        and not parsed.username
        and not parsed.password
        and parsed.path.rstrip("/") == path
        and not parsed.query
        and not parsed.fragment
    )


def validate_gemini_model(model: str, *, live: bool = False) -> None:
    """Allow only Gemini model names already approved by this application."""
    model = str(model or "").strip()
    allowed = _GEMINI_LIVE_MODELS if live else _GEMINI_TEXT_MODELS
    if model not in allowed:
        raise PolicyViolation(f"Gemini model is not approved: {model or '<empty>'}")


def validate_cloudflare_account_id(account_id: str) -> str:
    account_id = str(account_id or "").strip()
    if not _CLOUDFLARE_ACCOUNT_RE.fullmatch(account_id):
        raise PolicyViolation(
            "Cloudflare account ID must be exactly 32 hexadecimal characters"
        )
    return account_id.lower()


def validate_provider(provider_id: str, cfg: dict,
                      declaration: dict | None = None) -> PolicyDecision:
    """Validate a configured provider before importing or contacting it."""
    raw_id = str(provider_id or "").strip()
    base, _, entry = raw_id.partition("@")
    model = str((cfg or {}).get("model") or "").strip()
    url = str((cfg or {}).get("base_url") or "").strip()

    if base == "pipeline":
        return PolicyDecision(raw_id, model, True, True)
    if base not in {"openai_compat", "whisper", "piper", "system_tts"}:
        raise PolicyViolation(f"provider is not approved: {raw_id or '<empty>'}")

    catalog = (declaration or {}).get("catalog") or ()
    entry_row = next((row for row in catalog if row.get("id") == entry), None)
    if entry_row and entry_row.get("local") is True:
        if base == "openai_compat" and not _host_is_local(url):
            raise PolicyViolation(
                f"local provider must use loopback address: {entry}"
            )
        if base == "whisper" and (cfg or {}).get("backend") == "api":
            raise PolicyViolation(f"local provider cannot use an API backend: {entry}")
        if url and not _host_is_local(url):
            raise PolicyViolation(
                f"local provider must use loopback address: {entry}"
            )
        return PolicyDecision(raw_id, model, True, True)

    if base != "openai_compat":
        if base == "whisper" and entry == "groq":
            if not _is_official_https(url, "api.groq.com", "/openai/v1"):
                raise PolicyViolation(
                    "Groq Whisper requires the official HTTPS endpoint "
                    "/openai/v1"
                )
            if model not in {
                "whisper-large-v3-turbo",
                "whisper-large-v3",
            }:
                raise PolicyViolation(
                    "Groq Whisper is restricted to approved free-tier models"
                )
            return PolicyDecision(raw_id, model, False, True)
        raise PolicyViolation(
            f"paid or cost-unknown provider is blocked: {raw_id}"
        )

    # The unqualified id is a legacy configuration format. It is retained only
    # for private endpoints; hosted endpoints must use an explicitly approved
    # catalog entry.
    if not entry:
        if not _host_is_local(url) or not model:
            raise PolicyViolation(
                "legacy OpenAI-compatible providers must be local and configured"
            )
        return PolicyDecision(raw_id, model, True, True)

    local_entries = {"ollama", "lmstudio", "llamacpp", "vllm", "jan"}
    if entry in local_entries:
        if not _host_is_local(url):
            raise PolicyViolation(
                f"local provider must use a private address: {entry}"
            )
        if not model:
            raise PolicyViolation(f"local provider needs a model: {entry}")
        return PolicyDecision(raw_id, model, True, True)

    if entry == "custom":
        if not _host_is_local(url):
            raise PolicyViolation(
                "custom endpoints are blocked unless they use a private address"
            )
        if not model:
            raise PolicyViolation("custom local provider needs a model")
        return PolicyDecision(raw_id, model, True, True)

    if entry == "openrouter":
        if not _is_official_https(url, "openrouter.ai", "/api/v1"):
            raise PolicyViolation("OpenRouter requires the official HTTPS endpoint")
        if model != "openrouter/free" and not model.endswith(":free"):
            raise PolicyViolation(
                "OpenRouter is restricted to ':free' models or the openrouter/free alias"
            )
        return PolicyDecision(raw_id, model, False, True)

    if entry == "cloudflare":
        account_id = validate_cloudflare_account_id(
            (cfg or {}).get("account_id")
        )
        plan = str((cfg or {}).get("cloudflare_plan") or "").strip().lower()
        if plan != "free-confirmed":
            raise PolicyViolation(
                "Cloudflare is blocked until the account is manually confirmed "
                "as Workers Free. Paid or unknown accounts may generate charges."
            )
        expected_path = f"/client/v4/accounts/{account_id}/ai/v1"
        if not _is_official_https(
            url,
            "api.cloudflare.com",
            expected_path,
        ):
            raise PolicyViolation(
                "Cloudflare requires its official account-scoped HTTPS endpoint"
            )
        if model not in _CLOUDFLARE_FREE_CHAT_MODELS:
            raise PolicyViolation(
                "Cloudflare is restricted to approved free Workers AI chat models"
            )
        return PolicyDecision(raw_id, model, False, True)

    if entry == "groq":
        if not _is_official_https(url, "api.groq.com", "/openai/v1"):
            raise PolicyViolation("Groq requires the official HTTPS endpoint")
        if model not in _GROQ_FREE_MODELS:
            raise PolicyViolation(
                "Groq is restricted to the approved free-tier model list"
            )
        return PolicyDecision(raw_id, model, False, True)

    raise PolicyViolation(
        f"paid or cost-unknown provider is blocked: {entry}"
    )
