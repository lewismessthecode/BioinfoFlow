from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_token import AgentToken
from app.repositories.agent_harness_repo import RunFence
from app.repositories.agent_token_repo import AgentTokenRepository


DEFAULT_AGENT_TOKEN_TTL = timedelta(minutes=10)
MAX_AGENT_TOKEN_TTL = timedelta(hours=1)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AgentTokenGrant:
    """One plaintext token handoff; repr intentionally omits the secret."""

    token: str = field(repr=False)
    session_id: str
    run_id: str
    expires_at: datetime


@dataclass(frozen=True)
class AgentTokenContext:
    id: str
    user_id: str
    workspace_id: str
    project_id: str | None
    connection_id: str | None
    session_id: str
    run_id: str
    expires_at: datetime


class AgentTokenService:
    """Issue and validate scoped Agent credentials without storing plaintext."""

    def __init__(self, session: AsyncSession):
        self.repository = AgentTokenRepository(session)

    async def issue(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        run_id: str,
        fence: RunFence,
        ttl: timedelta = DEFAULT_AGENT_TOKEN_TTL,
        now: datetime | None = None,
    ) -> AgentTokenGrant:
        if ttl <= timedelta(0) or ttl > MAX_AGENT_TOKEN_TTL:
            raise ValueError("Agent token lifetime must be between 0 and 1 hour")
        issued_at = now or _utc_now()
        token = secrets.token_urlsafe(32)
        expires_at = issued_at + ttl
        await self.repository.replace_active(
            token_hash=_hash_token(token),
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            expires_at=expires_at,
            now=issued_at,
            fence=fence,
        )
        return AgentTokenGrant(
            token=token,
            session_id=session_id,
            run_id=run_id,
            expires_at=expires_at,
        )

    async def authenticate(
        self, token: str, *, now: datetime | None = None
    ) -> AgentTokenContext | None:
        binding = await self.repository.find_active(
            token_hash=_hash_token(token), now=now or _utc_now()
        )
        if binding is None:
            return None
        record, project_id, connection_id = binding
        return self._context(
            record,
            project_id=project_id,
            connection_id=connection_id,
        )

    async def revoke_run(
        self,
        run_id: str,
        *,
        fence: RunFence | None = None,
        now: datetime | None = None,
    ) -> None:
        await self.repository.revoke_run(
            run_id=run_id,
            fence=fence,
            now=now or _utc_now(),
        )

    async def revoke(self, token: str, *, now: datetime | None = None) -> None:
        await self.repository.revoke_token(
            token_hash=_hash_token(token), now=now or _utc_now()
        )

    async def rotate(
        self,
        token: str,
        *,
        fence: RunFence,
        ttl: timedelta = DEFAULT_AGENT_TOKEN_TTL,
        now: datetime | None = None,
    ) -> AgentTokenGrant:
        rotated_at = now or _utc_now()
        context = await self.authenticate(token, now=rotated_at)
        if context is None:
            raise ValueError("Cannot rotate an invalid Agent token")
        ttl_error = ttl <= timedelta(0) or ttl > MAX_AGENT_TOKEN_TTL
        if ttl_error:
            raise ValueError("Agent token lifetime must be between 0 and 1 hour")
        next_token = secrets.token_urlsafe(32)
        expires_at = rotated_at + ttl
        await self.repository.replace_active(
            token_hash=_hash_token(next_token),
            user_id=context.user_id,
            workspace_id=context.workspace_id,
            session_id=context.session_id,
            run_id=context.run_id,
            now=rotated_at,
            expires_at=expires_at,
            fence=fence,
            expected_token_hash=_hash_token(token),
        )
        return AgentTokenGrant(
            token=next_token,
            session_id=context.session_id,
            run_id=context.run_id,
            expires_at=expires_at,
        )

    async def revoke_session(
        self, session_id: str, *, now: datetime | None = None
    ) -> None:
        await self.repository.revoke_session(
            session_id=session_id, now=now or _utc_now()
        )

    @staticmethod
    def _context(
        record: AgentToken,
        *,
        project_id: str | None,
        connection_id: str | None,
    ) -> AgentTokenContext:
        return AgentTokenContext(
            id=str(record.id),
            user_id=record.user_id,
            workspace_id=record.workspace_id,
            project_id=project_id,
            connection_id=connection_id,
            session_id=record.session_id,
            run_id=record.run_id,
            expires_at=record.expires_at,
        )
