from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.schemas.file import FileType


class StorageSourceKind(str, Enum):
    PROJECT = "project"
    RESULTS = "results"
    DELIVERIES = "deliveries"
    REFERENCE = "reference"
    DATABASE = "database"


class AssetRef(BaseModel):
    kind: str = "asset_ref"
    uri: str
    label: str | None = None


class StorageSourceRead(BaseModel):
    id: str
    label: str
    kind: StorageSourceKind
    read_only: bool = True
    upload_allowed: bool = False
    scan_allowed: bool = True


class StorageFileInfo(BaseModel):
    name: str
    path: str
    uri: str
    type: FileType
    size_bytes: int | None = None
    modified_at: datetime | None = None


class StorageBrowseResponse(BaseModel):
    source: StorageSourceRead
    path: str
    files: list[StorageFileInfo]


class StorageReadResponse(BaseModel):
    uri: str
    content: str
    total_lines: int
    truncated: bool


class StorageUploadResponse(BaseModel):
    uri: str
    path: str


class StorageSampleFile(BaseModel):
    type: str
    uri: str
    path: str


class StorageSample(BaseModel):
    sample_id: str
    files: list[StorageSampleFile]


class StorageScanRequest(BaseModel):
    project_id: str
    source_id: str = "project"
    path: str = "."
    file_types: list[str] | None = None


class StorageScanResponse(BaseModel):
    source_id: str
    path: str
    detected_samples: list[StorageSample]
    file_format: str | None = None
    compression: str | None = None
    total_samples: int = 0


@dataclass(frozen=True)
class ResolvedStorageSource:
    source: StorageSourceRead
    root: str


@dataclass(frozen=True)
class ResolvedAsset:
    source: StorageSourceRead
    relative_path: str
    path: object
