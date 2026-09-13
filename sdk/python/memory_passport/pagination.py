"""Pagination helpers and iterators for Memory Passport Python SDK."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

from memory_passport.models.common import SyncPage

T = TypeVar("T")


class Paginator(Generic[T]):
    """Provides ergonomic iteration over offset/limit paginated endpoints."""

    def __init__(
        self,
        fetcher: Callable[[int, int], SyncPage[T] | list[T]],
        *,
        page_size: int = 50,
        initial_offset: int = 0,
        max_items: int | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._page_size = max(1, page_size)
        self._initial_offset = max(0, initial_offset)
        self._max_items = max_items

    def __iter__(self) -> Iterator[T]:
        offset = self._initial_offset
        yielded = 0

        while True:
            limit = self._page_size
            if self._max_items is not None:
                remaining = self._max_items - yielded
                if remaining <= 0:
                    break
                limit = min(limit, remaining)

            result = self._fetcher(offset, limit)

            if isinstance(result, SyncPage):
                items = result.items
            else:
                items = list(result)

            if not items:
                break

            for item in items:
                yield item
                yielded += 1
                if self._max_items is not None and yielded >= self._max_items:
                    return

            if len(items) < limit:
                break

            offset += len(items)
