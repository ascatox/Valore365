"""Small thread-safe in-memory TTL cache (Doctor 2.0 evaluations/scenarios).

Keys are tuples; the first two items are ``(user_id, scope_fingerprint)`` by
convention, so :meth:`TTLCache.invalidate_scope` can drop every entry of a
scope after a save. Values are stored as-is: callers store immutable objects
(Pydantic models they never mutate) or copy them on the way out.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any

DEFAULT_TTL_SECONDS = 60.0
DEFAULT_MAX_ENTRIES = 512


class TTLCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._ttl = float(ttl_seconds)
        self._max = int(max_entries)
        self._clock = clock
        self._data: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Hashable) -> Any | None:
        now = self._clock()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, value = entry
            if expires_at <= now:
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: Hashable, value: Any, *, ttl_seconds: float | None = None) -> None:
        ttl = self._ttl if ttl_seconds is None else float(ttl_seconds)
        if ttl <= 0:
            return
        expires_at = self._clock() + ttl
        with self._lock:
            self._data[key] = (expires_at, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def invalidate_scope(self, user_id: str, scope_fingerprint: str) -> int:
        """Drop every entry whose key starts with (user_id, scope_fingerprint)."""
        with self._lock:
            doomed = [
                k for k in self._data
                if isinstance(k, tuple) and len(k) >= 2 and k[0] == user_id and k[1] == scope_fingerprint
            ]
            for k in doomed:
                del self._data[k]
            return len(doomed)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
