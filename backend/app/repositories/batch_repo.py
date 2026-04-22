from __future__ import annotations

from sqlalchemy import select

from app.models.batch import Batch, BatchRun
from app.models.run import Run
from app.repositories.base import BaseRepository


class BatchRepository(BaseRepository[Batch]):
    model = Batch

    async def get_by_batch_id(self, batch_id: str) -> Batch | None:
        stmt = select(self.model).where(self.model.batch_id == batch_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_for_run(self, run_id: str) -> Batch | None:
        stmt = (
            select(Batch)
            .join(BatchRun, BatchRun.batch_id == Batch.id)
            .join(Run, Run.id == BatchRun.run_id)
            .where(Run.run_id == run_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_batch_runs(self, batch_id: str) -> list[BatchRun]:
        stmt = select(BatchRun).where(BatchRun.batch_id == batch_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class BatchRunRepository(BaseRepository[BatchRun]):
    model = BatchRun
