from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeAlias


StarterPromptSource: TypeAlias = Literal["cache", "fallback", "generated"]
logger = logging.getLogger(__name__)


class StarterPromptCache(Protocol):
    async def get(self, *, fingerprint: str, locale: str) -> Sequence[str] | None: ...

    async def set(
        self,
        *,
        fingerprint: str,
        locale: str,
        prompts: Sequence[str],
    ) -> None: ...


class InMemoryStarterPromptCache:
    def __init__(self, *, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._values: OrderedDict[tuple[str, str], tuple[str, ...]] = OrderedDict()

    async def get(self, *, fingerprint: str, locale: str) -> Sequence[str] | None:
        key = (fingerprint, locale)
        prompts = self._values.get(key)
        if prompts is not None:
            self._values.move_to_end(key)
        return prompts

    async def set(
        self,
        *,
        fingerprint: str,
        locale: str,
        prompts: Sequence[str],
    ) -> None:
        key = (fingerprint, locale)
        self._values[key] = tuple(prompts)
        self._values.move_to_end(key)
        while len(self._values) > self._max_entries:
            self._values.popitem(last=False)


@dataclass(frozen=True)
class StarterPromptGenerationRequest:
    fingerprint: str
    locale: str
    project: Mapping[str, Any]


StarterPromptGenerator: TypeAlias = Callable[
    [StarterPromptGenerationRequest], Awaitable[Sequence[str]]
]


@dataclass(frozen=True)
class StarterPromptResult:
    prompts: tuple[str, ...]
    fingerprint: str
    locale: str
    source: StarterPromptSource
    refresh_required: bool


_FALLBACKS = {
    "en": (
        "Review the project and suggest next steps",
        "Explain the workflows and inputs in this project",
        "Review recent runs and summarize the results",
    ),
    "zh-CN": (
        "检查项目并建议下一步",
        "解释项目中的工作流和输入",
        "查看最近运行并总结结果",
    ),
}
_MAX_PROMPTS = 3
_MAX_PROMPT_INPUT_CHARS = 4_096
_MAX_PROMPT_CHARS = 240
_MAX_PROJECT_SCALAR_BYTES = 2_048
_MAX_PROJECT_COLLECTION_ITEMS = 12
_MAX_PROJECT_COLLECTION_ITEM_BYTES = 512
_PROJECT_SCALAR_FIELDS = (
    "id",
    "name",
    "description",
    "storage_mode",
    "project_root",
    "instructions",
)
_PROJECT_COLLECTION_FIELDS = ("workflows", "recent_runs")


class StarterPromptService:
    def __init__(
        self,
        *,
        cache: StarterPromptCache,
        generate: StarterPromptGenerator | None,
    ) -> None:
        self._cache = cache
        self._generate = generate

    async def resolve(
        self, *, project: Mapping[str, Any], locale: str
    ) -> StarterPromptResult:
        normalized_locale = _normalize_locale(locale)
        fingerprint = project_prompt_fingerprint(project)
        try:
            cached = await self._cache.get(
                fingerprint=fingerprint,
                locale=normalized_locale,
            )
        except Exception:
            logger.warning("Starter prompt cache read failed", exc_info=True)
            cached = None
        normalized_cached = _normalize_prompts(cached or ())
        if normalized_cached:
            return StarterPromptResult(
                prompts=normalized_cached,
                fingerprint=fingerprint,
                locale=normalized_locale,
                source="cache",
                refresh_required=False,
            )
        return StarterPromptResult(
            prompts=_FALLBACKS[normalized_locale],
            fingerprint=fingerprint,
            locale=normalized_locale,
            source="fallback",
            refresh_required=self._generate is not None,
        )

    async def refresh(
        self, *, project: Mapping[str, Any], locale: str
    ) -> StarterPromptResult:
        normalized_locale = _normalize_locale(locale)
        bounded_project = _bounded_project_context(project)
        fingerprint = _fingerprint_bounded_project(bounded_project)
        fallback = StarterPromptResult(
            prompts=_FALLBACKS[normalized_locale],
            fingerprint=fingerprint,
            locale=normalized_locale,
            source="fallback",
            refresh_required=self._generate is not None,
        )
        if self._generate is None:
            return fallback
        try:
            generated = await self._generate(
                StarterPromptGenerationRequest(
                    fingerprint=fingerprint,
                    locale=normalized_locale,
                    project=bounded_project,
                )
            )
        except Exception:
            return fallback
        prompts = _normalize_prompts(generated)
        if not prompts:
            return fallback
        try:
            await self._cache.set(
                fingerprint=fingerprint,
                locale=normalized_locale,
                prompts=prompts,
            )
        except Exception:
            logger.warning("Starter prompt cache write failed", exc_info=True)
        return StarterPromptResult(
            prompts=prompts,
            fingerprint=fingerprint,
            locale=normalized_locale,
            source="generated",
            refresh_required=False,
        )


def project_prompt_fingerprint(project: Mapping[str, Any]) -> str:
    return _fingerprint_bounded_project(_bounded_project_context(project))


def _fingerprint_bounded_project(project: Mapping[str, Any]) -> str:
    payload = json.dumps(
        project,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bounded_project_context(project: Mapping[str, Any]) -> dict[str, Any]:
    bounded: dict[str, Any] = {}
    for field in _PROJECT_SCALAR_FIELDS:
        value = project.get(field)
        if value is None:
            continue
        text = _bounded_text(value, max_bytes=_MAX_PROJECT_SCALAR_BYTES)
        if text:
            bounded[field] = text
    for field in _PROJECT_COLLECTION_FIELDS:
        value = project.get(field)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            continue
        items = tuple(
            text
            for item in value[:_MAX_PROJECT_COLLECTION_ITEMS]
            if (
                text := _bounded_text(
                    item,
                    max_bytes=_MAX_PROJECT_COLLECTION_ITEM_BYTES,
                )
            )
        )
        if items:
            bounded[field] = items
    return bounded


def _bounded_text(value: Any, *, max_bytes: int) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, (int, float, bool)):
        text = str(value)
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    return text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def _normalize_locale(locale: str) -> str:
    return "zh-CN" if locale.lower().replace("_", "-").startswith("zh") else "en"


def _normalize_prompts(prompts: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_prompt in prompts:
        if not isinstance(raw_prompt, str):
            continue
        prompt = " ".join(raw_prompt[:_MAX_PROMPT_INPUT_CHARS].split())
        if not prompt:
            continue
        prompt = prompt[:_MAX_PROMPT_CHARS].rstrip()
        if prompt in seen:
            continue
        seen.add(prompt)
        normalized.append(prompt)
        if len(normalized) == _MAX_PROMPTS:
            break
    return tuple(normalized)
