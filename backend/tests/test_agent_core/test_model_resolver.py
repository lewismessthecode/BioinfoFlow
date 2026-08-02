from types import SimpleNamespace

import pytest

from app.services.agent_core.core.model_resolver import (
    AgentModelResolver,
    resolved_runtime_strategy,
    target_identity_matches_snapshot,
)


class _SelectionResolver(AgentModelResolver):
    def __init__(self, selections):
        self.selections = selections
        self.default_calls = 0

    async def catalog_selection(
        self,
        selection,
        *,
        source,
        workspace_id,
        user_id,
    ):
        self.selections.append((source, selection))
        if source == "turn":
            return {"model": "selected"}
        return None

    async def catalog_default_selection(self, *, workspace_id, user_id):
        self.default_calls += 1
        return {"model": "default"}


@pytest.mark.asyncio
async def test_resolver_stops_at_first_explicit_selection():
    calls = []
    resolver = _SelectionResolver(calls)
    turn = SimpleNamespace(
        user_id="user-1",
        model_profile_snapshot={
            "requested_model_selection": {"model_id": "model-1"}
        },
    )
    session = SimpleNamespace(
        workspace_id="workspace-1",
        default_model_profile_id=None,
        session_metadata=None,
    )

    result = await resolver.resolve_selection(turn=turn, session=session)

    assert result == {"model": "selected"}
    assert [source for source, _ in calls] == ["turn_profile", "turn"]
    assert resolver.default_calls == 0


def test_resolver_requires_the_persisted_target_revision():
    resolved = {
        "endpoint_id": "provider-1",
        "provider": "openai_compatible",
        "model": "model-1",
        "wire_protocol": "chat_completions",
        "request_args": {"api_base": "https://example.test/v1"},
        "target_revision": "revision-1",
    }
    snapshot = {
        "endpoint_id": "provider-1",
        "provider_kind": "openai_compatible",
        "model_name": "model-1",
        "wire_protocol": "chat_completions",
        "base_url": "https://example.test/v1",
    }

    assert target_identity_matches_snapshot(
        resolved,
        snapshot,
        expected_target_revision="revision-1",
    )
    assert not target_identity_matches_snapshot(
        resolved,
        snapshot,
        expected_target_revision="stale-revision",
    )


def test_resolved_runtime_strategy_normalizes_fallback_and_numeric_values():
    strategy = resolved_runtime_strategy(
        {
            "runtime_strategy": {
                "max_tokens": "2048",
                "reasoning_budget": "512",
                "reasoning_effort": "high",
                "fallback_model_ids": ["model-2", 3],
            }
        }
    )

    assert strategy.max_tokens == 2048
    assert strategy.reasoning_budget == 512
    assert strategy.reasoning_effort == "high"
    assert strategy.fallback_model_ids == ("model-2", "3")
