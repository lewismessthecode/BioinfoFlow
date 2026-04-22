from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class FileType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"


class FileInfo(BaseModel):
    name: str
    path: str
    type: FileType
    size_bytes: int | None = None
    modified_at: datetime | None = None
    children: list["FileInfo"] | None = None


class FileListResponse(BaseModel):
    path: str
    files: list[FileInfo]


class FileReadResponse(BaseModel):
    path: str
    content: str
    total_lines: int
    truncated: bool


class FileWriteRequest(BaseModel):
    project_id: str
    path: str
    content: str


class FileUploadResponse(BaseModel):
    path: str


class DetectedSampleFile(BaseModel):
    type: str
    path: str


class DetectedSample(BaseModel):
    sample_id: str
    files: list[DetectedSampleFile]


class FileScanRequest(BaseModel):
    project_id: str
    path: str = "."
    file_types: list[str] | None = None
    data_root: int | None = None


class FileScanResponse(BaseModel):
    path: str
    detected_samples: list[DetectedSample]
    file_format: str | None = None
    compression: str | None = None
    total_samples: int = 0


FileInfo.model_rebuild()
DetectedSample.model_rebuild()
