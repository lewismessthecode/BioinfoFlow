from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from app.services.agent_harness.starter_prompts import (
    StarterPromptGenerationRequest,
    StarterPromptResult,
    StarterPromptService,
    project_prompt_fingerprint,
)


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], tuple[str, ...]] = {}

    async def get(self, *, fingerprint: str, locale: str) -> Sequence[str] | None:
        return self.values.get((fingerprint, locale))

    async def set(
        self,
        *,
        fingerprint: str,
        locale: str,
        prompts: Sequence[str],
    ) -> None:
        self.values[(fingerprint, locale)] = tuple(prompts)


class _FailingCache:
    async def get(self, *, fingerprint: str, locale: str) -> Sequence[str] | None:
        raise RuntimeError("cache unavailable")

    async def set(
        self,
        *,
        fingerprint: str,
        locale: str,
        prompts: Sequence[str],
    ) -> None:
        raise RuntimeError("cache unavailable")


@pytest.mark.asyncio
async def test_cold_resolve_returns_localized_fallback_without_waiting_for_generation() -> (
    None
):
    generation_started = False

    async def generate(_request: StarterPromptGenerationRequest) -> Sequence[str]:
        nonlocal generation_started
        generation_started = True
        return ("generated",)

    service = StarterPromptService(cache=_MemoryCache(), generate=generate)

    first = await service.resolve(
        project={"id": "project-1", "name": "RNA demo"}, locale="zh-CN"
    )
    second = await service.resolve(
        project={"name": "RNA demo", "id": "project-1"}, locale="zh-CN"
    )

    assert first.prompts == (
        "检查这个项目",
        "了解可用的工作流",
        "查看最近一次运行",
    )
    assert second == first
    assert first.source == "fallback"
    assert first.refresh_required is True
    assert generation_started is False

    english = await service.resolve(
        project={"id": "project-1", "name": "RNA demo"}, locale="en-US"
    )
    assert english.prompts == (
        "Review this project",
        "Explore available workflows",
        "Check the latest run",
    )


@pytest.mark.asyncio
async def test_refresh_normalizes_generated_prompts_and_populates_cache() -> None:
    cache = _MemoryCache()
    received: list[StarterPromptGenerationRequest] = []

    async def generate(request: StarterPromptGenerationRequest) -> Sequence[str]:
        received.append(request)
        return (
            "  Inspect   the workflow  ",
            "Inspect the workflow",
            "\nReview recent runs\t",
            "Compare outputs",
            "A fourth unique suggestion is ignored",
        )

    service = StarterPromptService(cache=cache, generate=generate)
    project = {
        "id": "project-1",
        "name": "RNA demo",
        "description": "Quality-control and quantify RNA-seq reads",
    }

    refreshed = await service.refresh(project=project, locale="en-US")
    resolved = await service.resolve(project=project, locale="en")

    assert refreshed.prompts == (
        "Inspect the workflow",
        "Review recent runs",
        "Compare outputs",
    )
    assert refreshed.source == "generated"
    assert refreshed.refresh_required is False
    assert resolved == StarterPromptResult(
        prompts=refreshed.prompts,
        fingerprint=refreshed.fingerprint,
        locale="en",
        source="cache",
        refresh_required=False,
    )
    assert len(received) == 1
    assert received[0].project == {
        "name": "RNA demo",
        "description": "Quality-control and quantify RNA-seq reads",
    }


@pytest.mark.asyncio
async def test_refresh_keeps_internal_marker_in_cache_identity_but_never_exposes_it() -> (
    None
):
    marker = "bioinfoflow.demo.quickstart.v1"
    cache = _MemoryCache()
    received: list[StarterPromptGenerationRequest] = []

    async def generate(request: StarterPromptGenerationRequest) -> Sequence[str]:
        received.append(request)
        return (
            f"Inspect {marker}",
            "Review the quickstart workflow",
            "Check the sample inputs",
            "Summarize the latest run",
        )

    service = StarterPromptService(cache=cache, generate=generate)
    project = {
        "id": "project-1",
        "name": "BioinfoFlow Demo",
        "description": (
            f"Managed quickstart assets for the first analysis. Marker: {marker}"
        ),
        "project_root": "/private/internal/demo-root",
    }

    refreshed = await service.refresh(project=project, locale="en")
    resolved = await service.resolve(project=project, locale="en")

    assert refreshed.prompts == (
        "Review the quickstart workflow",
        "Check the sample inputs",
        "Summarize the latest run",
    )
    assert resolved.prompts == refreshed.prompts
    assert all(marker not in prompt for prompt in refreshed.prompts)
    assert received[0].fingerprint == project_prompt_fingerprint(project)
    assert marker not in json.dumps(received[0].project)
    assert received[0].project == {
        "name": "BioinfoFlow Demo",
        "description": "Managed quickstart assets for the first analysis.",
    }


@pytest.mark.asyncio
async def test_resolve_filters_internal_marker_from_an_existing_cache_entry() -> None:
    marker = "bioinfoflow.demo.quickstart.v1"
    project = {
        "id": "project-1",
        "name": "BioinfoFlow Demo",
        "description": f"Quickstart project. Marker: {marker}",
    }
    cache = _MemoryCache()
    cache.values[(project_prompt_fingerprint(project), "en")] = (
        f"Inspect {marker}",
        "Review the demo workflow",
        "Check the latest run",
    )

    async def generate(_request: StarterPromptGenerationRequest) -> Sequence[str]:
        return ("Regenerate clean prompts",)

    result = await StarterPromptService(cache=cache, generate=generate).resolve(
        project=project,
        locale="en",
    )

    assert result.prompts == (
        "Review the demo workflow",
        "Check the latest run",
    )
    assert result.source == "cache"
    assert result.refresh_required is True
    assert all(marker not in prompt for prompt in result.prompts)


@pytest.mark.asyncio
async def test_refresh_bounds_project_context_and_prompt_sizes() -> None:
    received: list[StarterPromptGenerationRequest] = []

    async def generate(request: StarterPromptGenerationRequest) -> Sequence[str]:
        received.append(request)
        return ("x" * 10_000, "second", "third", "fourth")

    service = StarterPromptService(cache=_MemoryCache(), generate=generate)
    project = {
        "id": "project-1",
        "name": "RNA demo",
        "description": "d" * 100_000,
        "workflows": [f"workflow-{index}-" + "w" * 2_000 for index in range(100)],
        "unrelated_secret": "must not enter the generation context",
    }

    result = await service.refresh(project=project, locale="en")

    assert len(result.prompts) == 3
    assert len(result.prompts[0]) == 80
    assert len(received) == 1
    assert len(str(received[0].project["description"]).encode()) <= 2_048
    assert len(received[0].project["workflows"]) <= 12
    assert "unrelated_secret" not in received[0].project


def test_project_fingerprint_is_deterministic_and_bounded() -> None:
    common_prefix = "d" * 2_048
    first = {
        "name": "RNA demo",
        "description": common_prefix + "ignored-a",
        "workflows": ["align", "quantify"],
    }
    reordered = {
        "workflows": ["align", "quantify"],
        "description": common_prefix + "ignored-b",
        "name": "RNA demo",
    }

    assert project_prompt_fingerprint(first) == project_prompt_fingerprint(reordered)
    assert project_prompt_fingerprint(first) != project_prompt_fingerprint(
        {**first, "name": "Different project"}
    )


@pytest.mark.asyncio
async def test_missing_or_failing_generator_returns_deterministic_fallback() -> None:
    project = {"id": "project-1", "name": "RNA demo"}
    unavailable = StarterPromptService(cache=_MemoryCache(), generate=None)

    async def fail(_request: StarterPromptGenerationRequest) -> Sequence[str]:
        raise RuntimeError("provider unavailable")

    failing = StarterPromptService(cache=_MemoryCache(), generate=fail)

    no_provider = await unavailable.refresh(project=project, locale="zh_Hans")
    provider_error = await failing.refresh(project=project, locale="zh-CN")

    assert no_provider.prompts == provider_error.prompts
    assert no_provider.source == provider_error.source == "fallback"
    assert no_provider.refresh_required is False
    assert provider_error.refresh_required is True


@pytest.mark.asyncio
async def test_cache_failure_does_not_break_fallback_or_generated_result() -> None:
    async def generate(_request: StarterPromptGenerationRequest) -> Sequence[str]:
        return ("Inspect the workflow",)

    service = StarterPromptService(cache=_FailingCache(), generate=generate)
    project = {"id": "project-1", "name": "RNA demo"}

    cold = await service.resolve(project=project, locale="en")
    refreshed = await service.refresh(project=project, locale="en")

    assert cold.source == "fallback"
    assert refreshed.source == "generated"
    assert refreshed.prompts == ("Inspect the workflow",)
