"""DoctorPolicyService and TTL cache with fakes (no database)."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.repository._scope import MIXED_CURRENCY_MESSAGE, NOT_FOUND_MESSAGE
from app.services.doctor_policy import service as service_module
from app.services.doctor_policy.cache import TTLCache
from app.services.doctor_policy.confirmation import ConsumedToken
from app.services.doctor_policy.errors import (
    ConfirmationInvalid,
    InvalidRequest,
    NotFound,
    PolicyValidationFailed,
)
from app.services.doctor_policy.service import DoctorPolicyService
from app.services.doctor_policy.snapshot import snapshot_from_holdings
from app.services.doctor_policy.store import PolicySetRecord

USER = "u1"
OWNED = {1: "EUR", 2: "EUR", 3: "USD"}
DOC = {
    "schema_version": 1,
    "rules": [{"rule_id": "max-single", "metric_code": "max_single_position_pct", "operator": "max", "max_value": 35}],
}
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


class _Repo:
    engine = object()

    def __init__(self) -> None:
        self.scope_calls: list[list[int]] = []

    def resolve_portfolio_scope(self, ids, user_id):
        self.scope_calls.append(list(ids))
        if user_id != USER or any(i not in OWNED for i in ids):
            raise ValueError(NOT_FOUND_MESSAGE)
        if len({OWNED[i] for i in ids}) > 1:
            raise ValueError(MIXED_CURRENCY_MESSAGE)


class _Store:
    def __init__(self) -> None:
        self.records: dict[str, PolicySetRecord] = {}
        self.saves = 0

    @contextmanager
    def transaction(self, conn=None):
        yield "conn"

    def get_policy_set(self, owner, fp, *, conn=None):
        rec = self.records.get(fp)
        return rec if rec and rec.owner_user_id == owner else None

    def get_policy_set_by_id(self, owner, pid, *, conn=None):
        return next((r for r in self.records.values() if r.id == pid and r.owner_user_id == owner), None)

    def save_version(self, *, owner_user_id, scope_fingerprint, portfolio_ids, name, document, base_version, **_kw):
        self.saves += 1
        prev = self.records.get(scope_fingerprint)
        version = (prev.current_version if prev else 0) + 1
        rec = PolicySetRecord(
            id=prev.id if prev else len(self.records) + 1, owner_user_id=owner_user_id, scope_type="single",
            scope_fingerprint=scope_fingerprint, name=name or (prev.name if prev else "x"), active=True,
            current_version=version, created_at=NOW, updated_at=NOW, archived_at=None,
            portfolio_ids=tuple(portfolio_ids), document=document,
        )
        self.records[scope_fingerprint] = rec
        return rec


@pytest.fixture()
def svc(monkeypatch):
    repo, store = _Repo(), _Store()
    builds = {"snapshot": 0, "metrics": 0}

    def fake_snapshot(_repo, ids, _user):
        builds["snapshot"] += 1
        return snapshot_from_holdings([], portfolio_ids=list(ids), base_currency="EUR")

    def fake_metrics(snapshot, _repo=None):
        builds["metrics"] += 1
        return {}

    monkeypatch.setattr(service_module, "build_snapshot", fake_snapshot)
    monkeypatch.setattr(service_module, "compute_metrics", fake_metrics)
    service = DoctorPolicyService(repo, store=store)
    return service, repo, store, builds


def test_scope_is_normalized_and_authorized(svc):
    service, repo, _store, _b = svc
    assert service.resolve_scope([2, "1", 2], USER) == [1, 2]
    assert repo.scope_calls[-1] == [1, 2]
    with pytest.raises(NotFound):
        service.resolve_scope([1, 99], USER)
    with pytest.raises(NotFound):
        service.resolve_scope([1], "intruder")
    with pytest.raises(InvalidRequest):
        service.resolve_scope([1, 3], USER)
    with pytest.raises(InvalidRequest):
        service.resolve_scope(list(range(1, 22)), USER)
    with pytest.raises(InvalidRequest):
        service.resolve_scope([], USER)


def test_evaluate_is_cached_and_invalidated_on_save(svc, monkeypatch):
    service, _repo, store, _b = svc
    evaluations = []
    real = service_module.build_evaluation_response

    def counting(*args, **kwargs):
        evaluations.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(service_module, "build_evaluation_response", counting)
    first = service.evaluate(USER, [1])
    assert first.status == "no_policy"
    service.evaluate(USER, [1])
    assert len(evaluations) == 1  # cache hit

    monkeypatch.setattr(service_module, "consume_token", lambda conn, **kw: ConsumedToken(source="manual"))
    service.save(USER, [1], name="P", document=DOC, base_version=None, confirmation_token="t")
    assert len(service.cache) == 0
    second = service.evaluate(USER, [1])
    assert second.policy_version == 1 and second.status == "empty_portfolio"
    assert len(evaluations) == 2


def test_evaluate_survives_freshness_failure(monkeypatch):
    """sync overview failing degrades data quality, never the evaluation."""
    from app.services.doctor_policy import snapshot as snapshot_module

    class _BrokenRepo(_Repo):
        def get_positions(self, pid, user_id):
            return []

        def get_market_data_sync_overview(self):
            raise RuntimeError("db down")

    repo = _BrokenRepo()
    monkeypatch.setattr(snapshot_module, "_load_scope", lambda r, ids, u: ("EUR", 0.0))
    service = DoctorPolicyService(repo, store=_Store())
    out = service.evaluate(USER, [1])
    assert out.status == "no_policy"
    assert out.data_quality.status == "unknown"


def test_save_requires_valid_document_and_token(svc, monkeypatch):
    service, _repo, store, _b = svc
    with pytest.raises(PolicyValidationFailed) as info:
        service.save(USER, [1], name="P", document={"rules": "x"}, base_version=None, confirmation_token="t")
    assert info.value.details["field_errors"]
    monkeypatch.setattr(service_module, "consume_token", lambda conn, **kw: None)
    with pytest.raises(ConfirmationInvalid):
        service.save(USER, [1], name="P", document=DOC, base_version=None, confirmation_token="t")
    assert store.saves == 0


def test_preview_same_snapshot_and_token_only_when_valid(svc, monkeypatch):
    service, _repo, _store, builds = svc
    issued = []

    def fake_issue(engine, **kw):
        issued.append(kw)
        return SimpleToken("tok", NOW)

    monkeypatch.setattr(service_module, "issue_token", fake_issue)
    out = service.preview(USER, [1], DOC, base_version=None, source="copilot")
    assert out.valid and out.confirmation_token == "tok" and out.evaluation_before is None
    assert out.evaluation_after is not None
    assert builds == {"snapshot": 1, "metrics": 1}
    assert issued[0]["source"] == "copilot" and issued[0]["scope_fingerprint"] == "p:1"
    bad = service.preview(USER, [1], {"schema_version": 1, "rules": [{"rule_id": "X!"}]})
    assert not bad.valid and bad.confirmation_token is None and bad.field_errors
    assert len(issued) == 1
    with pytest.raises(InvalidRequest):
        service.preview(USER, [1], DOC, source="restore")


def test_policy_by_id_unreadable_if_member_not_owned(svc):
    service, _repo, store, _b = svc
    rec = PolicySetRecord(
        id=7, owner_user_id=USER, scope_type="aggregate", scope_fingerprint="p:1,99", name="x", active=True,
        current_version=1, created_at=NOW, updated_at=NOW, archived_at=None, portfolio_ids=(1, 99), document=DOC,
    )
    store.records["p:1,99"] = rec
    with pytest.raises(NotFound):
        service.list_versions(USER, 7)
    with pytest.raises(NotFound):
        service.restore(USER, 7, version_number=1, base_version=1)
    store.records["p:1,99"] = replace(rec, owner_user_id="other")
    with pytest.raises(NotFound):
        service.list_versions(USER, 7)


def test_scenario_methods_validate_the_body(svc):
    # Scenario Lab is wired (tests/unit/test_doctor_scenario*.py): an empty body is a 400.
    service, *_ = svc
    with pytest.raises(InvalidRequest):
        service.preview_scenario(USER, {})
    with pytest.raises(InvalidRequest):
        service.compare_scenarios(USER, {})


class SimpleToken:
    def __init__(self, token, expires_at):
        self.token = token
        self.expires_at = expires_at


# --- TTL cache --------------------------------------------------------------


def test_ttl_cache_expiry_size_and_scope_invalidation():
    now = [0.0]
    cache = TTLCache(ttl_seconds=60, max_entries=2, clock=lambda: now[0])
    cache.set(("u", "p:1", 1), "a")
    cache.set(("u", "p:2", 1), "b")
    assert cache.get(("u", "p:1", 1)) == "a"
    cache.set(("u", "p:3", 1), "c")  # evicts LRU (p:2)
    assert cache.get(("u", "p:2", 1)) is None
    assert cache.invalidate_scope("u", "p:1") == 1
    assert cache.get(("u", "p:1", 1)) is None
    now[0] = 61
    assert cache.get(("u", "p:3", 1)) is None
    cache.set(("u", "p:4"), "x", ttl_seconds=0)
    assert len(cache) == 0


def test_ttl_cache_thread_safety():
    cache = TTLCache(ttl_seconds=60, max_entries=50)

    def worker(n):
        for i in range(500):
            cache.set(("u", f"p:{n}", i), i)
            cache.get(("u", f"p:{n}", i - 1))
            if i % 50 == 0:
                cache.invalidate_scope("u", f"p:{n}")

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(cache) <= 50
