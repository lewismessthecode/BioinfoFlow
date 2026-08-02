from __future__ import annotations

from fastapi import UploadFile


_READ_CHUNK_BYTES = 1024 * 1024


class UploadTooLargeError(ValueError):
    def __init__(self, max_bytes: int) -> None:
        super().__init__(f"Upload exceeds maximum size of {max_bytes} bytes")
        self.max_bytes = max_bytes


async def read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an upload incrementally and fail as soon as it exceeds its limit."""
    content = bytearray()
    while True:
        chunk = await upload.read(
            min(_READ_CHUNK_BYTES, max(1, max_bytes - len(content) + 1))
        )
        if not chunk:
            return bytes(content)
        content.extend(chunk)
        if len(content) > max_bytes:
            raise UploadTooLargeError(max_bytes)
