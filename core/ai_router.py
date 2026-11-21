"""Safe fallback routing for the local Pipeline LLM."""
from __future__ import annotations

import time
from typing import Any, AsyncIterator, Callable

from core.ai_errors import ErrorKind, classify_error
from core.ai_policy import validate_provider


TASK_PROFILES = ("conversation", "reasoning", "coding", "vision")


def classify_task_profile(messages: list[dict] | None = None,
                          tools: list[dict] | None = None) -> str:
    """Deterministically classify a task without making any model call."""
    has_image = AIRouter._requires_vision(messages or [])
    if has_image:
        return "vision"

    tool_names: set[str] = set()
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or "").lower()
        function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        name = name or str(function.get("name") or "").lower()
        if name:
            tool_names.add(name)

    text_parts: list[str] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
    text = " ".join(text_parts).lower()

    coding_markers = (
        "python", "javascript", "typescript", "c#", "golang", " rust ",
        "java ", "code", "source code", "bug", "debug", "traceback",
        "stack trace", "exception", "compile", "compiler", "refactor",
        "implement", "function", "class ", "programming", "git ",
        "pull request", "syntax", "dependency", "unit test",
        "write a script", "fix this", "patch",
    )
    for marker in coding_markers:
        if marker in f" {text} ":
            return "coding"

    reasoning_markers = (
        "reason", "prove", "derive", "plan ", "planning", "strategy",
        "analyze", "analyse", "analysis", "compare", "evaluation",
        "trade-off", "tradeoff", "architect", "step by step",
        "complex problem", "decision", "hypothesis",
    )
    research_tools = {"web_search", "google_search", "grounding"}
    if not (tool_names & research_tools):
        for marker in reasoning_markers:
            if marker in text:
                return "reasoning"

    return "conversation"


class AIRouter:
    """Try one primary LLM, then a short explicit list of authorized alternatives."""

    def __init__(
        self,
        primary_id: str,
        alternatives: list[str] | tuple[str, ...] = (),
        *,
        config_getter: Callable[[str], dict] | None = None,
        builder: Callable[[str, dict], Any] | None = None,
        config_setter: Callable[[str, dict], None] | None = None,
        preference_getter: Callable[[str], str] | None = None,
        selection_logger: Callable[[str, str], None] | None = None,
    ) -> None:
        self.primary_id = str(primary_id or "").strip()
        self.alternatives = tuple(str(pid).strip() for pid in alternatives
                                  if str(pid).strip())
        self._config_getter = config_getter
        self._builder = builder
        self._config_setter = config_setter
        self._preference_getter = preference_getter
        self._selection_logger = selection_logger
        self._cooldown: dict[str, float] = {}
        self._last: Any = None
        self._partial = False
        self.last_profile = "conversation"
        self.last_selected_provider = ""
        self.selection_log: list[tuple[str, str]] = []
        self.caps = {}
        self.caps.update({
            "tools": False,
            "tool_format": None,
            "vision": False,
            "max_tools": None,
            "max_tool_chars": None,
        })

    def _ids(self) -> list[str]:
        return self._ordered_ids("conversation", [], [])

    def _ordered_ids(self, profile: str,
                     messages: list[dict] | None = None,
                     tools: list[dict] | None = None) -> list[str]:
        preferred = ""
        if self._preference_getter is not None:
            try:
                preferred = str(self._preference_getter(profile) or "").strip()
            except Exception:
                preferred = ""
        elif hasattr(self, "_preferences"):
            preferred = str(self._preferences.get(profile) or "").strip()
        if not preferred:
            try:
                from memory.config_manager import get_task_router_preferences
                preferred = str(get_task_router_preferences().get(profile) or "").strip()
            except Exception:
                preferred = ""

        ids: list[str] = []
        for provider_id in (preferred, self.primary_id) + self.alternatives:
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
        if until:
            if time.monotonic() < until:
                return True
            self._cooldown.pop(provider_id, None)
            return False
        try:
            wall_until = float(self._config(provider_id).get("cooldown_until_wall") or 0)
        except (TypeError, ValueError):
            wall_until = 0.0
        if wall_until:
            if time.time() < wall_until:
                return True
            return False
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
        if self._config_setter is not None:
            try:
                self._config_setter(
                    provider_id,
                    {"cooldown_until_wall": float(time.time() + seconds)},
                )
            except Exception:
                pass

    def cooling_until(self, provider_id: str) -> float:
        return self._cooldown.get(provider_id, 0.0)

    def clear_cooldown(self, provider_id: str) -> None:
        self._cooldown.pop(provider_id, None)
        if self._config_setter is not None:
            try:
                self._config_setter(provider_id, {"cooldown_until_wall": 0})
            except Exception:
                pass

    def _fallback_allowed(self, info) -> bool:
        return info.recoverable and not self._partial

    @staticmethod
    def _requires_vision(messages: list[dict]) -> bool:
        for message in messages or []:
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    kind = str(part.get("type") or "").lower()
                    if kind in {"image", "image_url", "input_image"}:
                        return True
                    if "image_url" in part:
                        return True
            elif isinstance(content, dict):
                kind = str(content.get("type") or "").lower()
                if kind in {"image", "image_url", "input_image"}:
                    return True
        return False

    def _provider_caps(self, provider: Any) -> dict:
        return dict(getattr(provider, "caps", {}) or {})

    def _compatible(self, provider: Any, *,
                    requires_tools: bool,
                    requires_vision: bool) -> bool:
        caps = self._provider_caps(provider)
        if requires_tools and (
            not caps.get("tools")
            or not caps.get("tool_format")
        ):
            return False
        if requires_vision and not caps.get("vision"):
            return False
        return True

    def _copy_primary_caps(self, provider: Any) -> dict:
        caps = dict(self.caps)
        caps.update(self._provider_caps(provider))
        self.caps = caps
        self._last = provider
        return caps

    def ensure_vision_known(self, save=None) -> bool:
        provider_id = self._ordered_ids("vision")[0]
        try:
            provider = self._build(provider_id)
            self._copy_primary_caps(provider)
            check = getattr(provider, "ensure_vision_known", None)
            if check is None:
                seen = bool(self._provider_caps(provider).get("vision"))
            else:
                seen = bool(check(save))
            self.caps["vision"] = seen
            provider.caps = dict(self._provider_caps(provider))
            provider.caps["vision"] = seen
            return seen
        except Exception:
            self.caps["vision"] = False
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
        requires_tools = bool(tools)
        requires_vision = self._requires_vision(messages)
        profile = classify_task_profile(messages, tools)
        self.last_profile = profile

        for provider_id in self._ordered_ids(profile, messages, tools):
            if provider_id in attempted or self._cooling(provider_id):
                continue
            attempted.add(provider_id)
            cfg = self._config(provider_id)
            if str(cfg.get("enabled") or "1").strip().lower() in {"0", "false", "off", "disabled"}:
                continue

            try:
                provider = self._build(provider_id)
                if not self._compatible(
                    provider,
                    requires_tools=requires_tools,
                    requires_vision=requires_vision,
                ):
                    continue
                self._copy_primary_caps(provider)
                self.last_selected_provider = provider_id
                selection = (profile, provider_id)
                if selection not in self.selection_log:
                    self.selection_log.append(selection)
                if self._selection_logger is not None:
                    try:
                        self._selection_logger(profile, provider_id)
                    except Exception:
                        pass
                async for event in provider.chat(
                    messages,
                    tools,
                    stream=stream,
                    temperature=temperature,
                ):
                    usage = event.get("usage") if isinstance(event, dict) else None
                    if usage and self._config_setter is not None:
                        try:
                            accumulated = getattr(provider, "usage_accumulated", None)
                            values = {"usage": dict(usage)}
                            if isinstance(accumulated, dict):
                                values["usage_accumulated"] = dict(accumulated)
                            self._config_setter(provider_id, values)
                        except Exception:
                            pass
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
        requires_tools = bool(tools)
        requires_vision = self._requires_vision(messages)
        profile = classify_task_profile(messages, tools)
        self.last_profile = profile
        for provider_id in self._ordered_ids(profile, messages, tools):
            if provider_id in attempted or self._cooling(provider_id):
                continue
            attempted.add(provider_id)
            cfg = self._config(provider_id)
            if str(cfg.get("enabled") or "1").strip().lower() in {"0", "false", "off", "disabled"}:
                continue
            try:
                provider = self._build(provider_id)
                if not self._compatible(
                    provider,
                    requires_tools=requires_tools,
                    requires_vision=requires_vision,
                ):
                    continue
                self._copy_primary_caps(provider)
                self.last_selected_provider = provider_id
                selection = (profile, provider_id)
                if selection not in self.selection_log:
                    self.selection_log.append(selection)
                if self._selection_logger is not None:
                    try:
                        self._selection_logger(profile, provider_id)
                    except Exception:
                        pass
                text, calls = provider.complete(
                    messages,
                    tools,
                    timeout=timeout,
                    temperature=temperature,
                )
                usage = getattr(provider, "last_usage", None)
                if usage and self._config_setter is not None:
                    try:
                        accumulated = getattr(provider, "usage_accumulated", None)
                        values = {"usage": dict(usage)}
                        if isinstance(accumulated, dict):
                            values["usage_accumulated"] = dict(accumulated)
                        self._config_setter(provider_id, values)
                    except Exception:
                        pass
                return text, calls
            except Exception as exc:
                info = classify_error(exc, provider=provider_id)
                self._rest(provider_id, info)
                if not info.recoverable:
                    raise RuntimeError(info.message) from None
        raise RuntimeError("all AI providers failed")
