"""Safe fallback routing for the local Pipeline LLM."""
from __future__ import annotations

import time
from typing import Any, AsyncIterator, Callable

from core.ai_errors import ErrorKind, classify_error
from core.ai_policy import validate_provider


class AIRouter:
    """Try one primary LLM, then a short explicit list of authorized alternatives."""

    def __init__(
        self,
        primary_id: str,
        alternatives: list[str] | tuple[str, ...] = (),
        *,
        config_getter: Callable[[str], dict] | None = None,
        builder: Callable[[str, dict], Any] | None = None,
    ) -> None:
        self.primary_id = str(primary_id or "").strip()
        self.alternatives = tuple(str(pid).strip() for pid in alternatives
                                  if str(pid).strip())
        self._config_getter = config_getter
        self._builder = builder
        self._cooldown: dict[str, float] = {}
        self._last: Any = None
        self._partial = False
        self._build_caps = {}
        self.caps = {}

    def _ids(self) -> list[str]:
        ids: list[str] = []
        for provider_id in (self.primary_id,) + self.alternatives:
            if provider_id and provider_id not in ids:
                ids.append(provider_id)
        return ids

    def _config(self, provider_id: str) -> dict:
        if self._config_getter is not None:
            return dict(self._config_getter(provider_id) or {})
        from memory.config_manager import get_provider_config
        return get_provider_config(provider_id)

    def _build(self, provider_id: str) -> Any:
        cfg = self._config(provider_id)
        decl = None
        if self._builder is None:
            from providers import registry
            decl = registry.get_declaration(provider_id)
            validate_provider(provider_id, cfg, declaration=decl)
            missing = registry.missing_fields(provider_id, cfg)
            if missing:
                raise RuntimeError(f"404 not configured: {', '.join(missing)}")
            return registry.build(provider_id, cfg)

        validate_provider(provider_id, cfg)
        return self._builder(provider_id, cfg)

    def _cooling(self, provider_id: str) -> bool:
        until = self._cooldown.get(provider_id, 0.0)
        if until and time.monotonic() < until:
            return True
        self._cooldown.pop(provider_id, None)
        return False

    def _rest(self, provider_id: str, info) -> None:
        if info.kind in {ErrorKind.QUOTA_EXHAUSTED, ErrorKind.RATE_LIMITED}:
            seconds = 300
        elif info.kind == ErrorKind.UNAVAILABLE:
            seconds = 1800
        elif info.kind in {ErrorKind.TIMEOUT, ErrorKind.CONNECTION}:
            seconds = 60
        else:
            return
        self._cooldown[provider_id] = time.monotonic() + seconds

    def cooling_until(self, provider_id: str) -> float:
        return self._cooldown.get(provider_id, 0.0)

    def clear_cooldown(self, provider_id: str) -> None:
        self._cooldown.pop(provider_id, None)

    def _fallback_allowed(self, info) -> bool:
        return info.recoverable and not self._partial

    def ensure_vision_known(self, save=None) -> bool:
        provider_id = self.primary_id
        try:
            provider = self._build(provider_id)
            check = getattr(provider, "ensure_vision_known", None)
            if check is None:
                return bool(getattr(provider, "caps", {}).get("vision"))
            return bool(check(save))
        except Exception:
            return False

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        stream: bool = True,
        temperature: float | None = None,
    ) -> AsyncIterator[dict]:
        self._partial = False
        attempted: set[str] = set()

        for provider_id in self._ids():
            if provider_id in attempted or self._cooling(provider_id):
                continue
            attempted.add(provider_id)

            try:
                provider = self._build(provider_id)
                self._last = provider
                self.caps = dict(getattr(provider, "caps", {}) or {})
                async for event in provider.chat(
                    messages,
                    tools,
                    stream=stream,
                    temperature=temperature,
                ):
                    if event.get("text") or event.get("tool_calls"):
                        self._partial = True
                    yield event
                return
            except Exception as exc:
                info = classify_error(
                    exc,
                    provider=provider_id,
                    partial=self._partial,
                )
                self._rest(provider_id, info)
                if not self._fallback_allowed(info):
                    raise RuntimeError(info.message) from None

        raise RuntimeError("all AI providers failed")

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        *,
        timeout: float | None = None,
        temperature: float | None = None,
    ) -> tuple[str, list]:
        attempted: set[str] = set()
        for provider_id in self._ids():
            if provider_id in attempted or self._cooling(provider_id):
                continue
            attempted.add(provider_id)
            try:
                provider = self._build(provider_id)
                self._last = provider
                self.caps = dict(getattr(provider, "caps", {}) or {})
                return provider.complete(
                    messages,
                    tools,
                    timeout=timeout,
                    temperature=temperature,
                )
            except Exception as exc:
                info = classify_error(exc, provider=provider_id)
                self._rest(provider_id, info)
                if not info.recoverable:
                    raise RuntimeError(info.message) from None
        raise RuntimeError("all AI providers failed")
