from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_error_envelope(async_client):
    session_id = str(uuid4())
    response = await async_client.get(f"/api/v1/agent/sessions/{session_id}")
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "NOT_FOUND"
