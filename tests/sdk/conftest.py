"""Test fixtures and mock helpers for Memory Passport SDK tests."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

# Ensure sdk/python is in sys.path
sdk_path = Path(__file__).resolve().parent.parent.parent / "sdk" / "python"
if str(sdk_path) not in sys.path:
    sys.path.insert(0, str(sdk_path))

from memory_passport import MemoryPassportClient


class MockResponseHandler:
    """Mock handler that simulates HTTP responses based on route rules."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._routes: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}
        self._default_handler: Callable[[httpx.Request], httpx.Response] | None = None

    def register(
        self,
        method: str,
        path: str,
        status_code: int = 200,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            resp_headers = {"content-type": "application/json"}
            if headers:
                resp_headers.update(headers)
            content = json.dumps(json_data).encode("utf-8") if json_data is not None else b""
            return httpx.Response(status_code=status_code, headers=resp_headers, content=content)

        self._routes[(method.upper(), path)] = handler

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method.upper(), request.url.path)
        if key in self._routes:
            return self._routes[key](request)
        if self._default_handler:
            return self._default_handler(request)
        return httpx.Response(status_code=404, json={"detail": "Not found in mock handler"})


@pytest.fixture
def mock_handler() -> MockResponseHandler:
    return MockResponseHandler()


@pytest.fixture
def mock_client(mock_handler: MockResponseHandler) -> MemoryPassportClient:
    transport = httpx.MockTransport(mock_handler.handle)
    client = httpx.Client(base_url="http://testserver", transport=transport)
    return MemoryPassportClient(
        base_url="http://testserver",
        api_key="test-api-key",
        httpx_client=client,
    )
