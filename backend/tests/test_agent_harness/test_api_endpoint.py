from __future__ import annotations

import pytest

from app.services.agent_harness.api_endpoint import workspace_api_url


def test_local_workspace_api_url_has_development_default() -> None:
    assert workspace_api_url("local", configured_url=None) == (
        "http://127.0.0.1:8000/api/v1"
    )


def test_remote_workspace_requires_reachable_public_api_url() -> None:
    with pytest.raises(ValueError, match="must be configured"):
        workspace_api_url("remote_ssh", configured_url="")
    with pytest.raises(ValueError, match="cannot use localhost"):
        workspace_api_url(
            "remote_ssh",
            configured_url="http://127.0.0.1:8000/api/v1",
        )


def test_remote_workspace_accepts_configured_reachable_api_url() -> None:
    assert (
        workspace_api_url(
            "remote_ssh",
            configured_url="https://bioinfoflow.example/api/v1/",
        )
        == "https://bioinfoflow.example/api/v1"
    )


@pytest.mark.parametrize("value", ["bioinfoflow.example/api/v1", "ftp://host/api"])
def test_workspace_api_url_rejects_invalid_urls(value: str) -> None:
    with pytest.raises(ValueError, match="absolute HTTP"):
        workspace_api_url("local", configured_url=value)
