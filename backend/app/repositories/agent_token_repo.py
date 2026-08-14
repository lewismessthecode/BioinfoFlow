from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select, text, update

from app.models.agent_harness import AgentHarnessRun, AgentHarnessSession
from app.models.agent_token import AgentToken
from app.repositories.base import BaseRepository
from app.repositories.agent_harness_repo import RunFence


class AgentTokenRepository(BaseRepository[AgentToken]):
    model = AgentToken

    async def find_active(
        self, *, token_hash: str, now: datetime
    ) -> tuple[AgentToken, str | None, str | None] | None:
        result = await self.session.execute(
            select(
                self.model,
                AgentHarnessSession.project_id,
                AgentHarnessSession.workspace_snapshot,
            )
            .join(
                AgentHarnessSession,
                AgentHarnessSession.id == self.model.session_id,
            )
            .join(AgentHarnessRun, AgentHarnessRun.id == self.model.run_id)
            .where(
                self.model.token_hash == token_hash,
                self.model.revoked_at.is_(None),
                self.model.expires_at > now,
                AgentHarnessSession.status == "active",
                AgentHarnessSession.user_id == self.model.user_id,
                AgentHarnessSession.workspace_id == self.model.workspace_id,
                AgentHarnessRun.session_id == self.model.session_id,
                AgentHarnessRun.status.in_(("queued", "running")),
            )
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            return None
        snapshot = row[2] if isinstance(row[2], dict) else {}
        remote = snapshot.get("remote_connection")
        connection_id = (
            str(remote.get("id"))
            if isinstance(remote, dict) and remote.get("id") is not None
            else None
        )
        return (
            row[0],
            str(row[1]) if row[1] is not None else None,
            connection_id,
        )

    async def replace_active(
        self,
        *,
        token_hash: str,
        user_id: str,
        workspace_id: str,
        session_id: str,
        run_id: str,
        expires_at: datetime,
        now: datetime,
        fence: RunFence,
        expected_token_hash: str | None = None,
    ) -> AgentToken:
        """Atomically make one token the sole active credential for a run."""
        bind = self.session.get_bind()
        is_sqlite = bind.dialect.name == "sqlite"
        if is_sqlite:
            # SQLite ignores SELECT FOR UPDATE. BEGIN IMMEDIATE takes the write
            # reservation before reading or revoking so concurrent issuers are
            # serialized. Repository methods already own their commit boundary.
            if self.session.in_transaction():
                await self.session.commit()
            await self.session.execute(text("BEGIN IMMEDIATE"))
        try:
            binding_query = (
                select(AgentHarnessRun.id)
                .join(
                    AgentHarnessSession,
                    AgentHarnessSession.id == AgentHarnessRun.session_id,
                )
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status.in_(("queued", "running")),
                    AgentHarnessRun.lease_owner == fence.owner,
                    AgentHarnessRun.lease_generation == fence.generation,
                    AgentHarnessSession.id == session_id,
                    AgentHarnessSession.status == "active",
                    AgentHarnessSession.user_id == user_id,
                    AgentHarnessSession.workspace_id == workspace_id,
                )
            )
            if not is_sqlite:
                # PostgreSQL serializes issuers on the durable run row. The
                # partial unique index remains the final invariant.
                binding_query = binding_query.with_for_update()
            binding = await self.session.scalar(binding_query)
            if binding is None:
                raise ValueError(
                    "Agent token claims do not match an active Agent run or "
                    "stale Agent run fence"
                )

            if expected_token_hash is not None:
                claimed = await self.session.execute(
                    update(self.model)
                    .where(
                        self.model.token_hash == expected_token_hash,
                        self.model.run_id == run_id,
                        self.model.revoked_at.is_(None),
                        self.model.expires_at > now,
                    )
                    .values(revoked_at=now)
                )
                if claimed.rowcount != 1:
                    raise ValueError("Cannot rotate an invalid Agent token")

            await self.session.execute(
                update(self.model)
                .where(
                    self.model.run_id == run_id,
                    self.model.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            record = self.model(
                token_hash=token_hash,
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                run_id=run_id,
                expires_at=expires_at,
            )
            self.session.add(record)
            await self.session.commit()
            await self.session.refresh(record)
            return record
        except Exception:
            await self.session.rollback()
            raise

    async def revoke_run(
        self,
        *,
        run_id: str,
        now: datetime,
        fence: RunFence | None = None,
    ) -> None:
        if fence is None:
            await self._revoke_where(self.model.run_id == run_id, now=now)
            return
        bind = self.session.get_bind()
        is_sqlite = bind.dialect.name == "sqlite"
        if is_sqlite:
            if self.session.in_transaction():
                await self.session.commit()
            await self.session.execute(text("BEGIN IMMEDIATE"))
        try:
            run_query = select(AgentHarnessRun.id).where(
                AgentHarnessRun.id == run_id,
                AgentHarnessRun.lease_generation == fence.generation,
                or_(
                    AgentHarnessRun.lease_owner == fence.owner,
                    AgentHarnessRun.status.in_(("completed", "failed", "cancelled")),
                ),
            )
            if not is_sqlite:
                run_query = run_query.with_for_update()
            if await self.session.scalar(run_query) is None:
                raise ValueError("stale Agent run fence rejected token revocation")
            await self.session.execute(
                update(self.model)
                .where(
                    self.model.run_id == run_id,
                    self.model.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def revoke_token(self, *, token_hash: str, now: datetime) -> None:
        await self._revoke_where(self.model.token_hash == token_hash, now=now)

    async def revoke_session(self, *, session_id: str, now: datetime) -> None:
        await self._revoke_where(self.model.session_id == session_id, now=now)

    async def _revoke_where(self, clause, *, now: datetime) -> None:
        await self.session.execute(
            update(self.model)
            .where(clause, self.model.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self.session.commit()
