"""Share one execution among concurrent identical calls."""

import threading
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")


class _Call:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


class SingleFlight:
    """Runs a function once per key at a time: a caller arriving while it runs
    waits for that run and gets its result, or its exception, instead of
    starting another one. A call made after the run ends starts a new one."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[Hashable, _Call] = {}

    def run(self, key: Hashable, fn: Callable[[], T]) -> T:
        with self._lock:
            call = self._calls.get(key)
            leader = call is None
            if leader:
                call = self._calls[key] = _Call()

        if not leader:
            call.done.wait()
            if call.error is not None:
                raise call.error
            return call.result

        try:
            call.result = fn()
        except BaseException as exc:
            call.error = exc
            raise
        finally:
            with self._lock:
                del self._calls[key]
            call.done.set()
        return call.result
