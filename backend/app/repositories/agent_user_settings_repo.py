from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.agent_user_settings import AgentUserSettings
from app.repositories.base import BaseRepository


class AgentUserSettingsRepository(BaseRepository[AgentUserSettings]):
    model = AgentUserSettings

    async def get(
        self, workspace_id: str, user_id: str
    ) -> AgentUserSettings | None:
        statement = (
            select(self.model)
            .where(
                self.model.workspace_id == workspace_id,
                self.model.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        return await self.session.scalar(statement)

    async def upsert(
        self,
        *,
        workspace_id: str,
        user_id: str,
        custom_instructions: str,
    ) -> AgentUserSettings:
        dialect_name = self.session.bind.dialect.name
        insert = (
            postgresql_insert if dialect_name == "postgresql" else sqlite_insert
        )
        statement = insert(self.model).values(
            workspace_id=workspace_id,
            user_id=user_id,
            custom_instructions=custom_instructions,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[self.model.workspace_id, self.model.user_id],
            set_={
                "custom_instructions": custom_instructions,
                "updated_at": func.now(),
            },
        )
        await self.session.execute(statement)
        await self.session.commit()
        settings = await self.get(workspace_id, user_id)
        assert settings is not None
        return settings
