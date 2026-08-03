from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from urllib.parse import urlparse

import aiohttp
from aiohttp.abc import AbstractResolver

from app.models.notification import NotificationConfig
from app.models.project import Project
from app.repositories.notification_repo import NotificationRepository
from app.repositories.project_repo import ProjectRepository
from app.utils.authorization import can_access_project
from app.utils.logging import get_logger


logger = get_logger(__name__)

# Private/reserved IP networks that webhook URLs must not resolve to
_DENIED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("ff00::/8"),
]


@dataclass(frozen=True)
class _WebhookDestination:
    hostname: str
    port: int
    addresses: tuple[tuple[str, int], ...]


class _PinnedResolver(AbstractResolver):
    """Return only the addresses approved before the HTTP request started."""

    def __init__(self, destination: _WebhookDestination) -> None:
        self.destination = destination

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[dict[str, object]]:
        del host, family
        return [
            {
                "hostname": self.destination.hostname,
                "host": address,
                "port": port or self.destination.port,
                "family": address_family,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
            for address, address_family in self.destination.addresses
        ]

    async def close(self) -> None:
        return None


def _is_denied_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or any(
        ip in network for network in _DENIED_NETWORKS
    )


def _resolve_webhook_destination(url: str) -> _WebhookDestination | None:
    """Resolve and validate a webhook destination exactly once."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not hostname:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addr_infos = socket.getaddrinfo(
            hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
        addresses: list[tuple[str, int]] = []
        for family, _, _, _, sockaddr in addr_infos:
            ip = ipaddress.ip_address(sockaddr[0])
            if _is_denied_ip(ip):
                return None
            address = (str(ip), family)
            if address not in addresses:
                addresses.append(address)
        if not addresses:
            return None
        return _WebhookDestination(
            hostname=hostname,
            port=port,
            addresses=tuple(addresses),
        )
    except (socket.gaierror, ValueError, OSError):
        # If we can't resolve, deny by default
        return None


def _is_private_url(url: str) -> bool:
    """Return True if the URL resolves to a private/reserved IP address."""
    return _resolve_webhook_destination(url) is None


class NotificationService:
    def __init__(self, session) -> None:
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.repo = NotificationRepository(session)

    async def create_config(
        self,
        *,
        project_id: str,
        user_id: str,
        workspace_id: str,
        channel: str,
        trigger: str,
        config: dict,
        enabled: bool = True,
    ) -> NotificationConfig:
        project = await self._get_authorized_project(
            project_id, user_id=user_id, workspace_id=workspace_id
        )
        if project is None:
            raise FileNotFoundError("project not found")
        if channel != "webhook":
            raise ValueError("unsupported notification channel")
        if not (config.get("url") or "").strip():
            raise ValueError("webhook url is required")
        return await self.repo.create(
            project_id=project_id,
            channel=channel,
            trigger=trigger,
            config=config,
            enabled=enabled,
        )

    async def list_configs(
        self,
        *,
        user_id: str,
        workspace_id: str,
        project_id: str | None = None,
        trigger: str | None = None,
        enabled: bool | None = None,
    ) -> list[NotificationConfig]:
        if project_id is not None:
            project = await self._get_authorized_project(
                project_id, user_id=user_id, workspace_id=workspace_id
            )
            if project is None:
                return []
        return await self.repo.list_configs(
            project_id=project_id,
            trigger=trigger,
            enabled=enabled,
            workspace_id=workspace_id,
        )

    async def delete_config(
        self, notification_id: str, *, user_id: str, workspace_id: str
    ) -> bool:
        config = await self.repo.get(notification_id)
        if config is None:
            return False
        project = await self._get_authorized_project(
            config.project_id, user_id=user_id, workspace_id=workspace_id
        )
        if project is None:
            return False
        await self.repo.delete(config)
        return True

    async def notify(self, project_id: str, trigger: str, payload: dict) -> None:
        configs = await self.repo.list_configs(
            project_id=project_id,
            trigger=trigger,
            enabled=True,
        )
        for config in configs:
            if config.channel != "webhook":
                continue
            await self._send_webhook(config, payload)

    async def _send_webhook(self, config: NotificationConfig, payload: dict) -> None:
        url = (config.config or {}).get("url")
        if not url:
            return
        destination = _resolve_webhook_destination(url)
        if destination is None:
            logger.warning(
                "notification.webhook.ssrf_blocked",
                url=url,
                trigger=config.trigger,
            )
            return
        headers = dict((config.config or {}).get("headers") or {})
        try:
            connector = aiohttp.TCPConnector(
                resolver=_PinnedResolver(destination),
                use_dns_cache=False,
                ssl=True,
            )
            timeout = aiohttp.ClientTimeout(total=10.0)
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                trust_env=False,
            ) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    allow_redirects=False,
                )
                response.raise_for_status()
        except Exception:  # noqa: BLE001
            logger.exception(
                "notification.webhook.failed",
                url=url,
                trigger=config.trigger,
            )

    async def _get_authorized_project(
        self, project_id: str, *, user_id: str, workspace_id: str
    ) -> Project | None:
        project = await self.project_repo.get(project_id)
        if project is None or not can_access_project(
            project,
            user_id=user_id,
            workspace_id=workspace_id,
        ):
            return None
        return project
