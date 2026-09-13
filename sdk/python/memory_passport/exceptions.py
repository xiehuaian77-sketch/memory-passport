"""Exception hierarchy for Memory Passport Python SDK.

Strictly preserves security: no sensitive credentials, authorization headers,
tokens, or full request bodies are ever printed or attached to exceptions.
"""

from __future__ import annotations

from typing import Any


class MemoryPassportError(Exception):
    """Base exception for all Memory Passport SDK errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r})"


class NetworkError(MemoryPassportError):
    """Raised when transport-level connection fails, DNS fails, or times out."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class APIError(MemoryPassportError):
    """Base class for HTTP error responses from Memory Passport server."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str | None = None,
        details: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.details = details
        self.request_id = request_id

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"status_code={self.status_code}, "
            f"message={self.message!r}, "
            f"error_code={self.error_code!r})"
        )


class AuthenticationError(APIError):
    """HTTP 401: Authentication credentials missing, invalid, or expired."""


class AuthorizationError(APIError):
    """HTTP 403: Insufficient permissions or disabled by governance policy."""


class NotFoundError(APIError):
    """HTTP 404: Requested resource does not exist or belongs to another user."""


class ConflictError(APIError):
    """HTTP 409: Resource state conflict, cycle detected, or key duplication."""


class ValidationError(APIError):
    """HTTP 422: Request payload failed schema or business validation."""


class RateLimitError(APIError):
    """HTTP 429: Too many requests. May include retry_after in seconds."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 429,
        error_code: str | None = None,
        details: Any | None = None,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            details=details,
            request_id=request_id,
        )
        self.retry_after = retry_after


class ServerError(APIError):
    """HTTP 5xx: Internal server error or bad gateway."""
