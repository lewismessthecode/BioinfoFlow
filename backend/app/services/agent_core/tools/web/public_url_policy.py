from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlparse

from app.utils.exceptions import PermissionDeniedError


AddressResolver = Callable[[str], Awaitable[Iterable[str]]]

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
_METADATA_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata.google",
        "metadata.aws.internal",
        "metadata.azure.internal",
        "instance-data",
    }
)
_PUBLIC_URL_ERROR = "URL must resolve exclusively to a public URL address"


@dataclass(frozen=True)
class PublicUrl:
    url: str
    host: str


async def validate_public_url(
    url: str,
    *,
    resolver: AddressResolver | None = None,
) -> PublicUrl:
    raw_url = str(url).strip()
    try:
        parsed = urlparse(raw_url)
        host = (parsed.hostname or "").rstrip(".").lower()
        parsed.port
    except ValueError as exc:
        raise PermissionDeniedError(_PUBLIC_URL_ERROR) from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise PermissionDeniedError(_PUBLIC_URL_ERROR)
    if not host or parsed.username is not None or parsed.password is not None:
        raise PermissionDeniedError(_PUBLIC_URL_ERROR)
    _ensure_public_host_syntax(host)

    resolve = resolver or _resolve_addresses
    try:
        addresses = list(await resolve(host))
    except (OSError, ValueError, socket.gaierror) as exc:
        raise PermissionDeniedError(_PUBLIC_URL_ERROR) from exc
    if not addresses:
        raise PermissionDeniedError(_PUBLIC_URL_ERROR)
    try:
        if any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise PermissionDeniedError(_PUBLIC_URL_ERROR)
    except ValueError as exc:
        raise PermissionDeniedError(_PUBLIC_URL_ERROR) from exc
    return PublicUrl(url=raw_url, host=host)


def _ensure_public_host_syntax(host: str) -> None:
    if host in _METADATA_HOSTS:
        raise PermissionDeniedError(_PUBLIC_URL_ERROR)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if (
            host == "localhost"
            or host.endswith(".localhost")
            or "." not in host
            or any(host.endswith(suffix) for suffix in _INTERNAL_HOST_SUFFIXES)
        ):
            raise PermissionDeniedError(_PUBLIC_URL_ERROR)
        return
    if not address.is_global:
        raise PermissionDeniedError(_PUBLIC_URL_ERROR)


async def _resolve_addresses(host: str) -> set[str]:
    def resolve() -> set[str]:
        infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return {str(info[4][0]) for info in infos}

    return await asyncio.to_thread(resolve)


__all__ = ["AddressResolver", "PublicUrl", "validate_public_url"]
