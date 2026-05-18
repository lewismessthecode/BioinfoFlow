from __future__ import annotations

import traceback

from app.utils.responses import error_response, success_response


def test_success_response_redacts_traceback_payloads():
    try:
        raise RuntimeError("database password leaked in traceback")
    except RuntimeError:
        stack = traceback.format_exc()

    response = success_response({"traceback": stack})

    assert response.body
    assert b"database password" not in response.body
    assert b"[redacted]" in response.body


def test_error_response_redacts_traceback_details():
    details = {
        "nested": {
            "stack_trace": [
                "Traceback (most recent call last):",
                "RuntimeError: internal path /secret",
            ]
        }
    }

    response = error_response(
        code="INTERNAL_ERROR",
        message="Internal server error",
        details=details,
    )

    assert response.body
    assert b"/secret" not in response.body
    assert b"[redacted]" in response.body
