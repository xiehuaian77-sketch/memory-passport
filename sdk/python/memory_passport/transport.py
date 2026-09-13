"""Transport layer for Memory Passport Python SDK."""

from __future__ import annotations

# Standard library imports
import json
import logging
import time
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Self

# Third‑party imports
import httpx

# Local imports
from memory_passport.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    MemoryPassportError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)

logger = logging.getLogger("memory_passport.transport")


class MemoryPassportTransport:
    """HTTP transport wrapper around httpx.Client with robust error translation."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        access_token: str | None = None,
        timeout: float | httpx.Timeout = 30.0,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        write_timeout: float = 10.0,
        pool_timeout: float = 5.0,
        max_retries: int = 2,
        custom_headers: Mapping[str, str] | None = None,
        httpx_client: httpx.Client | None = None,
    ) -> None:
        clean_base = base_url.rstrip("/")
        self.base_url = clean_base

        # Resolve credential: api_key takes precedence or access_token
        self._credential = api_key or access_token
        self.max_retries = max(0, max_retries)

        if isinstance(timeout, httpx.Timeout):
            self.timeout = timeout
        else:
            self.timeout = httpx.Timeout(
                timeout=timeout,
                connect=connect_timeout,
                read=read_timeout,
                write=write_timeout,
                pool=pool_timeout,
            )

        headers = {
            "User-Agent": "memory-passport-python/0.1.0",
            "Accept": "application/json",
        }
        if self._credential:
            headers["Authorization"] = f"Bearer {self._credential}"
        if custom_headers:
            headers.update(custom_headers)

        self._default_headers = headers

        if httpx_client is not None:
            self._client = httpx_client
            # Merge default headers into provided client, overriding default httpx user-agent
            for k, v in headers.items():
                if k.lower() == "user-agent" or k not in self._client.headers:
                    self._client.headers[k] = v
        else:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
                follow_redirects=True,
            )
        self._owns_client = httpx_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
        self.close()

    def _map_http_error(self, response: httpx.Response) -> APIError:
        status_code = response.status_code
        request_id = response.headers.get("x-request-id")

        detail_msg = f"HTTP {status_code}"
        error_code = None
        details = None

        try:
            body = response.json()
            if isinstance(body, dict):
                error_code = body.get("error_code")
                details = body.get("detail") or body.get("details")
                if isinstance(details, str):
                    detail_msg = details
                elif isinstance(details, list) and details:
                    first_err = details[0]
                    if isinstance(first_err, dict) and "msg" in first_err:
                        detail_msg = first_err["msg"]
                    else:
                        detail_msg = str(details)
                elif "message" in body:
                    detail_msg = str(body["message"])
        except (ValueError, json.JSONDecodeError):
            detail_msg = response.text[:200] if response.text else f"HTTP {status_code}"

        if status_code == 401:
            return AuthenticationError(
                detail_msg,
                status_code=status_code,
                error_code=error_code,
                details=details,
                request_id=request_id,
            )
        if status_code == 403:
            return AuthorizationError(
                detail_msg,
                status_code=status_code,
                error_code=error_code,
                details=details,
                request_id=request_id,
            )
        if status_code == 404:
            return NotFoundError(
                detail_msg,
                status_code=status_code,
                error_code=error_code,
                details=details,
                request_id=request_id,
            )
        if status_code == 409:
            return ConflictError(
                detail_msg,
                status_code=status_code,
                error_code=error_code,
                details=details,
                request_id=request_id,
            )
        if status_code == 422:
            return ValidationError(
                detail_msg,
                status_code=status_code,
                error_code=error_code,
                details=details,
                request_id=request_id,
            )
        if status_code == 429:
            retry_after_str = response.headers.get("Retry-After")
            retry_after: float | None = None
            if retry_after_str:
                try:
                    retry_after = float(retry_after_str)
                except ValueError:
                    retry_after = None
            return RateLimitError(
                detail_msg,
                status_code=status_code,
                error_code=error_code,
                details=details,
                request_id=request_id,
                retry_after=retry_after,
            )
        if status_code >= 500:
            return ServerError(
                detail_msg,
                status_code=status_code,
                error_code=error_code,
                details=details,
                request_id=request_id,
            )

        return APIError(
            detail_msg,
            status_code=status_code,
            error_code=error_code,
            details=details,
            request_id=request_id,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> Any:
        """Execute HTTP request with safe retry for GET requests."""
        is_safe_method = method.upper() in ("GET", "HEAD")
        attempts = 0
        max_attempts = (1 + self.max_retries) if is_safe_method else 1

        clean_params = None
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}

        last_error: Exception | None = None

        while attempts < max_attempts:
            attempts += 1
            try:
                response = self._client.request(
                    method=method,
                    url=path,
                    params=clean_params,
                    json=json,
                    headers=headers,
                    timeout=timeout or self.timeout,
                )

                if response.status_code >= 400:
                    api_error = self._map_http_error(response)
                    if (
                        is_safe_method
                        and attempts < max_attempts
                        and (response.status_code in (502, 503, 504) or response.status_code == 429)
                    ):
                        wait_sec = 0.2 * (2 ** (attempts - 1))
                        if isinstance(api_error, RateLimitError) and api_error.retry_after:
                            wait_sec = api_error.retry_after
                        time.sleep(min(wait_sec, 2.0))
                        continue
                    raise api_error

                if response.status_code == 204:
                    return None

                try:
                    return response.json()
                except Exception as exc:
                    raise MemoryPassportError(
                        f"Failed to parse server JSON response: {exc}"
                    ) from exc

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as net_err:
                last_error = NetworkError(f"Network error during {method} {path}: {net_err}", cause=net_err)
                if is_safe_method and attempts < max_attempts:
                    time.sleep(0.2 * (2 ** (attempts - 1)))
                    continue
                raise last_error from net_err

            except httpx.HTTPError as http_err:
                last_error = NetworkError(f"HTTP transport error during {method} {path}: {http_err}", cause=http_err)
                if is_safe_method and attempts < max_attempts:
                    time.sleep(0.2 * (2 ** (attempts - 1)))
                    continue
                raise last_error from http_err

        if last_error:
            raise last_error
        raise MemoryPassportError(f"Request failed after {attempts} attempts")
