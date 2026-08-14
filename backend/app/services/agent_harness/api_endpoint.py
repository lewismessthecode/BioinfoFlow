from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


_LOCAL_DEFAULT = "http://127.0.0.1:8000/api/v1"


def workspace_api_url(
    runtime: str,
    *,
    configured_url: str | None,
) -> str:
    """Resolve the API endpoint exposed to `bif` in a workspace runtime."""
    value = str(configured_url or "").strip()
    if not value:
        if runtime == "remote_ssh":
            raise ValueError(
                "BIOINFOFLOW_PUBLIC_API_BASE_URL must be configured with an "
                "address reachable from remote Agent workspaces"
            )
        return _LOCAL_DEFAULT
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Agent API URL must be an absolute HTTP(S) URL")
    if runtime == "remote_ssh" and _is_loopback_host(parsed.hostname):
        raise ValueError(
            "BIOINFOFLOW_PUBLIC_API_BASE_URL cannot use localhost for a remote "
            "Agent workspace"
        )
    return value.rstrip("/")


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


__all__ = ["workspace_api_url"]
