from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class WorkflowSource(str, Enum):
    NFCORE = "nf-core"
    GITHUB = "github"
    LOCAL = "local"


class WorkflowEngine(str, Enum):
    NEXTFLOW = "nextflow"
    WDL = "wdl"


class Workflow(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint(
            "source", "name", "version", name="uq_workflows_source_name_version"
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[WorkflowSource] = mapped_column(String(20), nullable=False)
    engine: Mapped[WorkflowEngine] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(500))
    entrypoint_relpath: Mapped[str | None] = mapped_column(String(500))
    bundle_kind: Mapped[str | None] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    estimated_time: Mapped[str | None] = mapped_column(String(100))
    schema_json: Mapped[dict | None] = mapped_column(JSON)
    form_spec: Mapped[dict | None] = mapped_column(JSON)
    weight: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    runs = relationship("Run", back_populates="workflow")
