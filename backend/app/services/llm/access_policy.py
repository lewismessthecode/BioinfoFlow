from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from app.services.model_runtime.contracts import NetworkAccessPolicy
from app.utils.authorization import can_manage_server_integrations
from app.utils.exceptions import PermissionDeniedError


# Names that conventionally resolve only within a machine, private network, or
# service mesh. DNS is also resolved immediately before an untrusted caller can
# trigger network I/O, so a public-looking hostname cannot bypass this static
# check by resolving to a private address.
_INTERNAL_HOST_SUFFIXES = (
    ".local",
    ".internal",
    ".intranet",
    ".lan",
    ".home",
    ".home.arpa",
    ".corp",
    ".svc",
    ".test",
)


def authorize_server_environment_credential(*, role: str | None) -> None:
    if can_manage_server_integrations(role):
        return
    raise PermissionDeniedError(
        "Server environment credentials require owner/admin access"
    )


async def authorize_provider_endpoint(
    base_url: str | None,
    *,
    role: str | None,
    resolve_dns: bool = False,
) -> None:
    """Authorize an actor to configure or contact a provider endpoint.

    URL syntax and transport security are validated separately. This policy is
    about server authority: team members may use public endpoints, while only
    trusted operators may target loopback, private, link-local, reserved, or
    internal service addresses.
    """
    await resolve_provider_network_access(
        base_url,
        private_endpoint_authorized=can_manage_server_integrations(role),
        resolve_dns=resolve_dns,
    )


async def resolve_provider_network_access(
    base_url: str | None,
    *,
    private_endpoint_authorized: bool,
    resolve_dns: bool = False,
) -> NetworkAccessPolicy:
    """Resolve transport policy independently from provider visibility.

    Shared catalog scope and credential authority decide whether an actor may
    use a provider configuration. They must not turn an otherwise public URL
    into unrestricted network access. Only an explicitly internal URL may use
    the unrestricted transport, and only after trusted configuration authority
    has been established by the caller.
    """
    if not base_url:
        return "public_only"
    parsed = urlparse(str(base_url).strip())
    host = parsed.hostname or ""
    if _is_non_public_host(host):
        if not private_endpoint_authorized:
            _deny_internal_endpoint()
        return "unrestricted"
    if resolve_dns:
        addresses = await asyncio.to_thread(_resolve_host_addresses, host)
        for address in addresses:
            if not address.is_global:
                # A public-looking hostname resolving privately is ambiguous,
                # not an explicit operator-selected internal endpoint. Fail
                # closed instead of upgrading it to unrestricted transport.
                _deny_internal_endpoint()
    return "public_only"


def _is_non_public_host(host: str) -> bool:
    if not host:
        return True
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        normalized = host.rstrip(".").lower()
        if normalized == "localhost" or normalized.endswith(".localhost"):
            return True
        if "." not in normalized:
            return True
        return any(normalized.endswith(suffix) for suffix in _INTERNAL_HOST_SUFFIXES)


def _resolve_host_addresses(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        addr_infos = socket.getaddrinfo(
            host,
            None,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
        addresses = {ipaddress.ip_address(info[4][0]) for info in addr_infos}
    except (socket.gaierror, ValueError, OSError) as exc:
        raise PermissionDeniedError(
            "Provider endpoint could not be resolved to an authorized public address"
        ) from exc
    if not addresses:
        raise PermissionDeniedError(
            "Provider endpoint could not be resolved to an authorized public address"
        )
    return addresses


def _deny_internal_endpoint() -> None:
    raise PermissionDeniedError(
        "Local and internal provider endpoints require owner/admin access"
    )
