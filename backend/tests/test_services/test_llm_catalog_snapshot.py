from app.services.llm.registry import load_catalog_snapshot


EXPECTED_IDS = {
    "openai",
    "anthropic",
    "openrouter",
    "fireworks",
    "qwen",
    "deepseek",
    "xai",
    "zai",
    "kimi-code",
    "minimax",
    "huggingface",
    "gemini",
}


def test_snapshot_contains_exact_phase_one_providers() -> None:
    snapshot = load_catalog_snapshot()

    assert set(snapshot) == EXPECTED_IDS


def test_snapshot_contains_only_agent_capable_text_models() -> None:
    snapshot = load_catalog_snapshot()

    for models in snapshot.values():
        assert all(model.supports_tools for model in models)
        assert all(model.output_modalities == ("text",) for model in models)


def test_snapshot_is_stably_sorted_and_has_unique_model_ids() -> None:
    snapshot = load_catalog_snapshot()

    for models in snapshot.values():
        ids = [model.id for model in models]
        assert ids == sorted(ids)
        assert len(ids) == len(set(ids))


def test_kimi_snapshot_is_pinned_to_official_coding_models() -> None:
    snapshot = load_catalog_snapshot()

    assert [model.id for model in snapshot["kimi-code"]] == [
        "k3",
        "kimi-for-coding",
        "kimi-for-coding-highspeed",
    ]
