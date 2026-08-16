from app.services.agent_session_title import derive_automatic_session_title


def test_title_derivation_uses_the_first_meaningful_text_part() -> None:
    assert (
        derive_automatic_session_title(
            ["  \n ", "Summarize this very long workflow request with many details"]
        )
        == "Summarize this very long"
    )


def test_title_derivation_preserves_chinese_and_is_deterministic() -> None:
    text_parts = ["检查 RNA 测序流程并修复样本表解析问题"]

    first = derive_automatic_session_title(text_parts)
    second = derive_automatic_session_title(text_parts)

    assert first == "检查 RNA 测序流程并修复样本表解析问题"
    assert second == first
