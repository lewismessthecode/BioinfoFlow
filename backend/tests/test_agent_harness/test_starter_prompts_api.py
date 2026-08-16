from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.services.agent_harness.starter_prompts import StarterPromptGenerationRequest


@pytest.mark.asyncio
async def test_starter_prompts_endpoint_returns_fallback_without_a_provider(
    async_client,
    db_session,
) -> None:
    from tests.support.path_contract import create_project

    project = await create_project(
        db_session,
        name=f"starter-prompts-{uuid4()}",
    )

    response = await async_client.get(
        "/api/v1/agent/starter-prompts",
        params={"project_id": str(project.id), "locale": "zh-CN"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "prompts": [
            "检查这个项目",
            "了解可用的工作流",
            "查看最近一次运行",
        ],
        "source": "fallback",
        "refresh_pending": True,
    }


@pytest.mark.asyncio
async def test_starter_prompts_endpoint_hides_unknown_projects(async_client) -> None:
    response = await async_client.get(
        "/api/v1/agent/starter-prompts",
        params={"project_id": str(uuid4()), "locale": "en"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_starter_prompts_endpoint_caches_background_generation_by_fingerprint(
    async_client,
    db_session,
) -> None:
    from tests.support.path_contract import create_project

    project = await create_project(
        db_session,
        name=f"generated-starter-prompts-{uuid4()}",
    )
    requests: list[StarterPromptGenerationRequest] = []

    async def generate(request: StarterPromptGenerationRequest) -> Sequence[str]:
        requests.append(request)
        return ("Inspect workflow inputs", "Review recent runs")

    with patch(
        "app.api.v1.agent_starter_prompts.build_starter_prompt_generator",
        return_value=generate,
    ):
        first = await async_client.get(
            "/api/v1/agent/starter-prompts",
            params={"project_id": str(project.id), "locale": "en"},
        )
        second = await async_client.get(
            "/api/v1/agent/starter-prompts",
            params={"project_id": str(project.id), "locale": "en"},
        )

    assert first.json()["data"]["source"] == "fallback"
    assert second.json()["data"] == {
        "prompts": ["Inspect workflow inputs", "Review recent runs"],
        "source": "cache",
        "refresh_pending": False,
    }
    assert len(requests) == 1
