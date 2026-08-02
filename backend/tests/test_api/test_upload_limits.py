from io import BytesIO

import pytest
from fastapi import UploadFile

from app.api.upload_limits import UploadTooLargeError, read_upload_limited


@pytest.mark.asyncio
async def test_read_upload_limited_reads_in_chunks() -> None:
    upload = UploadFile(BytesIO(b"abcdefghij"), filename="data.txt")

    content = await read_upload_limited(upload, 10)

    assert content == b"abcdefghij"


@pytest.mark.asyncio
async def test_read_upload_limited_stops_after_limit() -> None:
    upload = UploadFile(BytesIO(b"abcdefghijk"), filename="data.txt")

    with pytest.raises(UploadTooLargeError):
        await read_upload_limited(upload, 10)
