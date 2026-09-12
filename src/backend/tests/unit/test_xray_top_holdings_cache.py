import threading
import time

from app.services.portfolio_doctor._xray import _TopHoldingsCache


def _cache(ttl: float = 60.0, max_entries: int = 128) -> _TopHoldingsCache:
    return _TopHoldingsCache(ttl_seconds=ttl, max_entries=max_entries)


def test_a_symbol_is_fetched_once_within_the_ttl():
    cache = _cache()
    calls = []

    def fetch():
        calls.append(1)
        return [{"symbol": "AAPL", "weight": 0.1}]

    first = cache.get_or_fetch("VWCE", fetch)
    second = cache.get_or_fetch("VWCE", fetch)

    assert first == second
    assert len(calls) == 1


def test_an_empty_answer_is_cached_too():
    # A plain share is not a fund, so Yahoo returns nothing — and it was asked
    # again on every request precisely because nothing was stored.
    cache = _cache()
    calls = []

    def fetch():
        calls.append(1)
        return []

    assert cache.get_or_fetch("AAPL", fetch) == []
    assert cache.get_or_fetch("AAPL", fetch) == []
    assert len(calls) == 1


def test_simultaneous_lookups_of_one_symbol_fetch_once():
    cache = _cache()
    calls = []
    barrier = threading.Barrier(6)

    def fetch():
        calls.append(1)
        time.sleep(0.05)
        return [{"symbol": "MSFT", "weight": 0.2}]

    results = []

    def call():
        barrier.wait()
        results.append(cache.get_or_fetch("VWCE", fetch))

    threads = [threading.Thread(target=call) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1
    assert all(r == [{"symbol": "MSFT", "weight": 0.2}] for r in results)


def test_different_symbols_are_not_serialised_behind_each_other():
    cache = _cache()
    calls = []

    def fetch_for(symbol):
        def fetch():
            calls.append(symbol)
            return [{"symbol": symbol}]
        return fetch

    assert cache.get_or_fetch("A", fetch_for("A")) == [{"symbol": "A"}]
    assert cache.get_or_fetch("B", fetch_for("B")) == [{"symbol": "B"}]

    assert calls == ["A", "B"]


def test_entries_expire():
    cache = _cache(ttl=0.05)
    calls = []

    def fetch():
        calls.append(1)
        return []

    cache.get_or_fetch("VWCE", fetch)
    time.sleep(0.1)
    cache.get_or_fetch("VWCE", fetch)

    assert len(calls) == 2


def test_the_cache_stays_bounded():
    cache = _cache(ttl=300.0, max_entries=4)

    for i in range(20):
        cache.get_or_fetch(f"SYM{i}", lambda: [])

    assert len(cache._entries) <= 4
    assert len(cache._locks) <= 4
