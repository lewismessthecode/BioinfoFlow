from __future__ import annotations

import ipaddress
import socket

from app.utils.exceptions import PermissionDeniedError


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
_PUBLIC_ADDRESS_ERROR = (
    "Provider endpoint could not be resolved to an authorized public address"
)


def ensure_public_network_host(host: str) -> None:
    if not host:
        raise PermissionDeniedError(_PUBLIC_ADDRESS_ERROR)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        normalized = host.rstrip(".").lower()
        if (
            normalized == "localhost"
            or normalized.endswith(".localhost")
            or "." not in normalized
            or any(normalized.endswith(suffix) for suffix in _INTERNAL_HOST_SUFFIXES)
        ):
            raise PermissionDeniedError(_PUBLIC_ADDRESS_ERROR)
        return
    if not address.is_global:
        raise PermissionDeniedError(_PUBLIC_ADDRESS_ERROR)


def resolve_public_address_infos(
    host: str,
    port: int | None,
    *,
    family: int = socket.AF_UNSPEC,
) -> list[tuple[int, int, int, str, tuple]]:
    ensure_public_network_host(host)
    try:
        addr_infos = socket.getaddrinfo(
            host,
            port,
            family,
            socket.SOCK_STREAM,
        )
    except (socket.gaierror, ValueError, OSError) as exc:
        raise PermissionDeniedError(_PUBLIC_ADDRESS_ERROR) from exc
    if not addr_infos:
        raise PermissionDeniedError(_PUBLIC_ADDRESS_ERROR)
    for info in addr_infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError, TypeError) as exc:
            raise PermissionDeniedError(_PUBLIC_ADDRESS_ERROR) from exc
        if not address.is_global:
            raise PermissionDeniedError(_PUBLIC_ADDRESS_ERROR)
    return addr_infos


__all__ = ["ensure_public_network_host", "resolve_public_address_infos"]
