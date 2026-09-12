import app.auth as auth


def _reset() -> None:
    with auth._app_user_sync_lock:
        auth._app_user_synced_at.clear()


def test_repeated_requests_from_one_user_write_once_per_ttl(monkeypatch):
    # Every authenticated request used to open a write transaction, so a single
    # dashboard load produced a handful of identical app_users updates.
    _reset()
    writes: list[str] = []
    monkeypatch.setattr(auth, "engine", _RecordingEngine(writes))

    for _ in range(10):
        auth._sync_app_user("user_a", "a@example.com", None)

    assert writes == ["user_a"]


def test_each_user_is_throttled_independently(monkeypatch):
    _reset()
    writes: list[str] = []
    monkeypatch.setattr(auth, "engine", _RecordingEngine(writes))

    auth._sync_app_user("user_a", None, None)
    auth._sync_app_user("user_b", None, None)
    auth._sync_app_user("user_a", None, None)

    assert writes == ["user_a", "user_b"]


def test_sync_resumes_once_the_ttl_expires(monkeypatch):
    _reset()
    writes: list[str] = []
    monkeypatch.setattr(auth, "engine", _RecordingEngine(writes))

    clock = {"now": 1000.0}
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock["now"])

    auth._sync_app_user("user_a", None, None)
    clock["now"] += auth._APP_USER_SYNC_TTL / 2
    auth._sync_app_user("user_a", None, None)
    clock["now"] += auth._APP_USER_SYNC_TTL
    auth._sync_app_user("user_a", None, None)

    assert writes == ["user_a", "user_a"]


def test_a_failed_write_is_retried_rather_than_suppressed(monkeypatch):
    # The marker is set before the write, so a failure must clear it or the
    # user would go unsynced for the rest of the TTL.
    _reset()
    attempts: list[str] = []

    class _FailingEngine:
        def begin(self):
            attempts.append("try")
            raise RuntimeError("db down")

    monkeypatch.setattr(auth, "engine", _FailingEngine())

    auth._sync_app_user("user_a", None, None)
    auth._sync_app_user("user_a", None, None)

    assert len(attempts) == 2


class _RecordingConn:
    def __init__(self, writes: list[str]) -> None:
        self.writes = writes

    def execute(self, statement, params):
        self.writes.append(params["user_id"])


class _BeginContext:
    def __init__(self, conn) -> None:
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _RecordingEngine:
    def __init__(self, writes: list[str]) -> None:
        self.writes = writes

    def begin(self):
        return _BeginContext(_RecordingConn(self.writes))
