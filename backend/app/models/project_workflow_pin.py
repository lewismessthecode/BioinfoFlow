from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProjectWorkflowPin(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "project_workflow_pins"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "workflow_source",
            "workflow_name",
            name="uq_project_workflow_pins_project_source_name",
        ),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_source: Mapped[str] = mapped_column(String(20), nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(200), nullable=False)
    pinned_workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )

    project = relationship("Project")
    pinned_workflow = relationship("Workflow")
