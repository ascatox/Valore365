import threading
import time

import pytest

from app.single_flight import SingleFlight


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.005)


def _start_leader(flight, key, fn):
    """Run ``fn`` under ``key`` in a thread and return once it is running."""
    outcome = {}
    running = threading.Event()

    def leader_fn():
        running.set()
        return fn()

    def target():
        try:
            outcome["result"] = flight.run(key, leader_fn)
        except Exception as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    assert running.wait(2.0)
    return thread, outcome


def _start_follower(flight, key, fn):
    """Call ``run`` under ``key`` in a thread and return once it waits on the leader."""
    outcome = {}

    def target():
        try:
            outcome["result"] = flight.run(key, fn)
        except Exception as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    # CPython's Event keeps its waiting threads on the condition's waiter list.
    _wait_until(lambda: len(flight._calls[key].done._cond._waiters) == 1)
    return thread, outcome


def test_concurrent_calls_with_the_same_key_share_one_run():
    flight = SingleFlight()
    release = threading.Event()
    calls = []

    def fn():
        calls.append(1)
        release.wait(2.0)
        return {"refreshed": 14}

    leader, leader_outcome = _start_leader(flight, ("refresh", "user", 26), fn)
    follower, follower_outcome = _start_follower(flight, ("refresh", "user", 26), fn)
    release.set()
    leader.join(2.0)
    follower.join(2.0)

    assert len(calls) == 1
    assert leader_outcome == {"result": {"refreshed": 14}}
    assert follower_outcome["result"] is leader_outcome["result"]


def test_concurrent_callers_get_the_exception_of_the_shared_run():
    flight = SingleFlight()
    release = threading.Event()

    def fn():
        release.wait(2.0)
        raise ValueError("Portfolio non trovato")

    leader, leader_outcome = _start_leader(flight, "key", fn)
    follower, follower_outcome = _start_follower(flight, "key", fn)
    release.set()
    leader.join(2.0)
    follower.join(2.0)

    assert isinstance(leader_outcome["error"], ValueError)
    assert follower_outcome["error"] is leader_outcome["error"]


def test_different_keys_run_independently():
    flight = SingleFlight()
    release = threading.Event()

    leader, _ = _start_leader(flight, ("refresh", "user", 26), lambda: release.wait(2.0))

    assert flight.run(("refresh", "user", 27), lambda: "other portfolio") == "other portfolio"
    release.set()
    leader.join(2.0)


def test_calls_after_a_run_ends_start_a_new_one():
    flight = SingleFlight()
    calls = []

    def fn():
        calls.append(1)
        return len(calls)

    assert flight.run("key", fn) == 1
    assert flight.run("key", fn) == 2
    with pytest.raises(RuntimeError):
        flight.run("key", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert flight.run("key", fn) == 3
    assert flight._calls == {}
