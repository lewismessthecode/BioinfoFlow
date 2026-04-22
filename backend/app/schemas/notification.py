from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class NotificationChannel(str, Enum):
    WEBHOOK = "webhook"


class NotificationTrigger(str, Enum):
    ON_COMPLETE = "on_complete"
    ON_FAILURE = "on_failure"
    ON_BATCH_COMPLETE = "on_batch_complete"


class NotificationConfigCreate(BaseModel):
    project_id: UUID
    channel: NotificationChannel
    trigger: NotificationTrigger
    config: dict
    enabled: bool = True


class NotificationConfigRead(NotificationConfigCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime
