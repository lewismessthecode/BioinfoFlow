from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProjectWorkflowBinding(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "project_workflow_bindings"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "workflow_id",
            name="uq_project_workflow_bindings_project_workflow",
        ),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )

    project = relationship("Project")
    workflow = relationship("Workflow")
