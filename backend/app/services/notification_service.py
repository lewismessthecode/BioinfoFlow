from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app.models.notification import NotificationConfig
from app.repositories.project_repo import ProjectRepository
from app.repositories.notification_repo import NotificationRepository
from app.utils.logging import get_logger


logger = get_logger(__name__)

# Private/reserved IP networks that webhook URLs must not resolve to
_DENIED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_url(url: str) -> bool:
    """Return True if the URL resolves to a private/reserved IP address."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return True
        # Resolve hostname to IP addresses
        addr_infos = socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
        for family, _, _, _, sockaddr in addr_infos:
            ip = ipaddress.ip_address(sockaddr[0])
            if any(ip in network for network in _DENIED_NETWORKS):
                return True
    except (socket.gaierror, ValueError, OSError):
        # If we can't resolve, deny by default
        return True
    return False


class NotificationService:
    def __init__(self, session) -> None:
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.repo = NotificationRepository(session)

    async def create_config(
        self,
        *,
        project_id: str,
        channel: str,
        trigger: str,
        config: dict,
        enabled: bool = True,
    ) -> NotificationConfig:
        project = await self.project_repo.get(project_id)
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
        project_id: str | None = None,
        trigger: str | None = None,
        enabled: bool | None = None,
    ) -> list[NotificationConfig]:
        return await self.repo.list_configs(
            project_id=project_id,
            trigger=trigger,
            enabled=enabled,
        )

    async def delete_config(self, notification_id: str) -> bool:
        config = await self.repo.get(notification_id)
        if config is None:
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
        if _is_private_url(url):
            logger.warning(
                "notification.webhook.ssrf_blocked",
                url=url,
                trigger=config.trigger,
            )
            return
        headers = dict((config.config or {}).get("headers") or {})
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except Exception:  # noqa: BLE001
            logger.exception(
                "notification.webhook.failed",
                url=url,
                trigger=config.trigger,
            )
