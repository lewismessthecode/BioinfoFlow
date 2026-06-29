from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class BadRequestError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__("BAD_REQUEST", message, 400, details)


class NotFoundError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__("NOT_FOUND", message, 404, details)


class PermissionDeniedError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__("PERMISSION_DENIED", message, 403, details)


class ConflictError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__("CONFLICT", message, 409, details)


class ValidationError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__("VALIDATION_ERROR", message, 422, details)


class ConfigurationError(AppError):
    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__("CONFIGURATION_ERROR", message, 503, details)


_HTTP_ERROR_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}


def http_error_code(status_code: int) -> str:
    code = _HTTP_ERROR_CODES.get(status_code)
    if code is not None:
        return code
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "HTTP_ERROR"
