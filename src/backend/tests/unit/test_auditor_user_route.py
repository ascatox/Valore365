"""TASK-81: endpoint utente in sola lettura sugli esiti della corsa notturna dell'Auditor.

``GET /api/doctor/auditor/summary``: ``require_auth``, proprietà dello scope (singolo e aggregato)
come nel Doctor, regola delle 48 ore, esito peggiore per regola, titoli e aree dal registro, nessun
id di regola, severità o id della corsa nel payload; registrazione nell'app vera.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import routes_auditor_user as routes
from app.api.routes_auditor_user import build_summary, register_auditor_user_routes, worst_status_by_rule
from app.auth import AuthContext, require_auth
from app.errors import AppError
from app.repository._scope import MIXED_CURRENCY_MESSAGE, NOT_FOUND_MESSAGE
from app.services.auditor.registry import AREAS, RULE_ID_PATTERN, Rule, load_rules

PATH = "/api/doctor/auditor/summary"
NOW = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)
FINISHED = "2026-11-11T00:05:00+00:00"


def _rule(rule_id: str, title: str, area: str, severity: str = "P1") -> Rule:
    return Rule(
        id=rule_id, group=rule_id[0], title=title, area=area, severity=severity, findings=(),
        scopes=("portfolio",), tools=("get_positions",), check=lambda ctx, scope: {"status": "pass"},
    )


RULES = [
    _rule("A-STRESS-SIGN", "Gli scenari di stress hanno il segno atteso", "stress"),
    _rule("B-PAC-SUM", "Le quote del PAC sommano al totale", "rebalance"),
    _rule("B-REB-CASH", "Il ribilanciamento non supera la liquidità", "rebalance"),
    _rule("C-COST-TER", "Il costo annuo è coerente con i TER", "costs", "P0"),
    _rule("D-AGG-SUM", "La vista aggregata somma i portafogli", "aggregate"),
]


def _row(pid, rule_id, status, scope_kind="portfolio", severity="P1"):
    return {"portfolio_id": pid, "rule_id": rule_id, "scope_kind": scope_kind, "status": status, "severity": severity}


ROWS = [
    _row(1, "A-STRESS-SIGN", "pass"),
    _row(1, "B-PAC-SUM", "pass"),
    _row(1, "B-REB-CASH", "skip"),
    _row(1, "C-COST-TER", "error"),
    _row(2, "A-STRESS-SIGN", "pass"),
    _row(2, "B-PAC-SUM", "fail"),
    _row(2, "D-AGG-SUM", "pass", "aggregate"),
    _row(1, "D-AGG-SUM", "pass", "aggregate"),
]


class FakeRepo:
    def __init__(self, owned=None, currencies=None):
        self.owned = owned if owned is not None else {"user-1": {1, 2}}
        self.currencies = currencies or {}
        self.calls = []

    def resolve_portfolio_scope(self, ids, user_id):
        self.calls.append((list(ids), user_id))
        if any(pid not in self.owned.get(user_id, set()) for pid in ids):
            raise ValueError(NOT_FOUND_MESSAGE)
        if len({self.currencies.get(pid, "EUR") for pid in ids}) > 1:
            raise ValueError(MIXED_CURRENCY_MESSAGE)
        return SimpleNamespace(portfolio_ids=tuple(ids))


class FakeStore:
    def __init__(self, run=None, rows=None, finished_at=FINISHED, fail=False):
        self.run = run if run is not None else {
            "run_id": "a" * 32, "status": "completed_with_failures",
            "started_at": "2026-11-10T23:35:00+00:00", "finished_at": finished_at,
        }
        self.rows = ROWS if rows is None else rows
        self.fail = fail
        self.calls = []

    def latest_results_for_portfolios(self, ids):
        self.calls.append(list(ids))
        if self.fail:
            raise RuntimeError("db down")
        wanted = set(ids)
        return {"run": self.run or None, "rows": [r for r in self.rows if r["portfolio_id"] in wanted]}


def _client(store=None, repo=None, rules=RULES, user="user-1", now=NOW):
    store = store or FakeStore()
    repo = repo or FakeRepo()
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _app_error(_request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

    router = APIRouter()
    loads = []

    def loader():
        loads.append(1)
        return rules

    register_auditor_user_routes(router, repo, store_getter=lambda: store, rules_loader=loader, now=lambda: now)
    app.include_router(router, prefix="/api")
    if user is not None:
        app.dependency_overrides[require_auth] = lambda: AuthContext(user_id=user, org_id=None, email=None, claims={})
    return TestClient(app), store, repo, loads


# ---------------------------------------------------------------------------
# Calcolo
# ---------------------------------------------------------------------------


def test_worst_status_per_rule_across_portfolios_and_scope_kinds():
    rows = [
        _row(1, "B-PAC-SUM", "pass"), _row(2, "B-PAC-SUM", "skip"), _row(3, "B-PAC-SUM", "error"),
        _row(1, "A-X", "pass"), _row(1, "A-X", "fail", "instrument"),
        _row(1, "C-Y", "skip"), _row(1, "C-Y", "pass", "aggregate"),
        _row(1, "D-Z", "bogus"),
    ]
    assert worst_status_by_rule(rows) == {"B-PAC-SUM": "error", "A-X": "fail", "C-Y": "skip"}


def test_single_portfolio_summary():
    body = build_summary(FakeStore().latest_results_for_portfolios([1]), RULES, now=NOW)
    assert body["available"] is True
    assert body["run_finished_at"] == FINISHED
    # pass: A-STRESS-SIGN, B-PAC-SUM, D-AGG-SUM; skip e error non contano.
    assert (body["checks_passed"], body["checks_in_review"]) == (3, 0)
    assert [a["area"] for a in body["areas"]] == ["stress", "rebalance", "aggregate"]
    rebalance = body["areas"][1]
    assert rebalance == {
        "area": "rebalance", "label": AREAS["rebalance"], "status": "passed",
        "checks": [{"title": "Le quote del PAC sommano al totale", "status": "passed"}],
    }


def test_aggregate_union_takes_the_worst_outcome():
    body = build_summary(FakeStore().latest_results_for_portfolios([1, 2]), RULES, now=NOW)
    assert (body["checks_passed"], body["checks_in_review"]) == (2, 1)
    # L'area in verifica viene per prima, con il controllo in verifica in cima.
    first = body["areas"][0]
    assert first["area"] == "rebalance" and first["status"] == "in_review"
    assert first["checks"] == [{"title": "Le quote del PAC sommano al totale", "status": "in_review"}]
    assert {a["area"]: a["status"] for a in body["areas"][1:]} == {"stress": "passed", "aggregate": "passed"}


def test_areas_follow_registry_order_and_checks_sort_by_title():
    rules = [_rule("A-B", "Zeta", "stress"), _rule("A-A", "alfa", "stress"), _rule("C-A", "Costo", "costs")]
    rows = [_row(1, "A-B", "pass"), _row(1, "A-A", "pass"), _row(1, "C-A", "pass")]
    body = build_summary({"run": {"finished_at": FINISHED}, "rows": rows}, rules, now=NOW)
    assert [a["area"] for a in body["areas"]] == ["stress", "costs"]
    assert [c["title"] for c in body["areas"][0]["checks"]] == ["alfa", "Zeta"]


@pytest.mark.parametrize("finished_at, available", [
    ((NOW - timedelta(hours=47, minutes=59)).isoformat(), True),
    ((NOW - timedelta(hours=48)).isoformat(), True),
    ((NOW - timedelta(hours=48, seconds=1)).isoformat(), False),
    ((NOW - timedelta(days=5)).isoformat(), False),
    ("2026-11-11T00:05:00Z", True),
    ("2026-11-11T00:05:00", True),  # senza fuso = UTC
    (None, False),
    ("non-una-data", False),
])
def test_48_hour_rule(finished_at, available):
    body = build_summary({"run": {"finished_at": finished_at}, "rows": ROWS}, RULES, now=NOW)
    assert body["available"] is available
    if not available:
        assert body == routes.unavailable()


def test_no_run_or_no_visible_check_means_unavailable():
    assert build_summary({"run": None, "rows": []}, RULES, now=NOW) == routes.unavailable()
    # Solo skip/error, o regole non più nel registro: niente da mostrare.
    rows = [_row(1, "B-REB-CASH", "skip"), _row(1, "C-COST-TER", "error"), _row(1, "A-GONE", "fail")]
    assert build_summary({"run": {"finished_at": FINISHED}, "rows": rows}, RULES, now=NOW)["available"] is False


def test_rule_missing_from_registry_is_not_shown_and_never_leaks_its_id():
    rows = [_row(1, "A-STRESS-SIGN", "pass"), _row(1, "A-GONE", "fail")]
    body = build_summary({"run": {"finished_at": FINISHED}, "rows": rows}, RULES, now=NOW)
    assert (body["checks_passed"], body["checks_in_review"]) == (1, 0)
    assert "A-GONE" not in json.dumps(body)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def _assert_no_internals(payload: dict) -> None:
    text = json.dumps(payload)
    assert not re.search(RULE_ID_PATTERN.strip("^$"), text), text
    for forbidden in ("rule_id", "severity", "P0", "P1", "P2", "run_id", "portfolio_id", "a" * 32, "evidence"):
        assert forbidden not in text, forbidden
    assert set(payload) == {"available", "run_finished_at", "checks_passed", "checks_in_review", "areas"}
    for area in payload["areas"]:
        assert set(area) == {"area", "label", "status", "checks"}
        assert area["status"] in {"passed", "in_review"}
        for check in area["checks"]:
            assert set(check) == {"title", "status"}
            assert check["status"] in {"passed", "in_review"}


def test_single_and_aggregate_scope_over_rest():
    client, store, repo, loads = _client()
    single = client.get(PATH, params={"portfolio_id": 1})
    assert single.status_code == 200
    assert single.json()["checks_passed"] == 3
    _assert_no_internals(single.json())
    aggregate = client.get(PATH, params={"portfolio_ids": "2,1"})
    assert aggregate.status_code == 200 and aggregate.json()["checks_in_review"] == 1
    _assert_no_internals(aggregate.json())
    repeated = client.get(f"{PATH}?portfolio_ids=1&portfolio_ids=2")
    assert repeated.json() == aggregate.json()
    assert store.calls == [[1], [1, 2], [1, 2]]
    assert repo.calls[0] == ([1], "user-1") and repo.calls[1] == ([1, 2], "user-1")
    # Il registro si carica una volta.
    assert loads == [1]


def test_requires_auth():
    client, store, _, _ = _client(user=None)
    client.app.dependency_overrides[require_auth] = lambda: (_ for _ in ()).throw(
        AppError(code="unauthorized", message="Missing token", status_code=401),
    )
    assert client.get(PATH, params={"portfolio_id": 1}).status_code == 401
    assert store.calls == []


def test_foreign_portfolio_is_404_single_and_aggregate():
    client, store, _, _ = _client(repo=FakeRepo(owned={"user-1": {1, 2}, "user-2": {3}}))
    for params in ({"portfolio_id": 3}, {"portfolio_ids": "1,3"}, {"portfolio_ids": "3"}):
        response = client.get(PATH, params=params)
        assert response.status_code == 404, params
        assert response.json()["error"]["code"] == "not_found"
    assert store.calls == []


@pytest.mark.parametrize("query", ["", "?portfolio_ids=", "?portfolio_id=abc", "?portfolio_id=0", "?portfolio_id=-4",
                                   "?portfolio_ids=" + ",".join(str(i) for i in range(1, 22))])
def test_invalid_scope_is_400(query):
    client, store, _, _ = _client(repo=FakeRepo(owned={"user-1": set(range(1, 30))}))
    response = client.get(PATH + query)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert store.calls == []


def test_mixed_currency_aggregate_is_400_like_the_doctor():
    client, _, _, _ = _client(repo=FakeRepo(currencies={1: "EUR", 2: "USD"}))
    assert client.get(PATH, params={"portfolio_ids": "1,2"}).status_code == 400


def test_stale_or_missing_run_returns_unavailable():
    old = (NOW - timedelta(days=3)).isoformat()
    client, _, _, _ = _client(store=FakeStore(finished_at=old))
    assert client.get(PATH, params={"portfolio_id": 1}).json() == routes.unavailable()
    client, _, _, _ = _client(store=FakeStore(run={}))
    assert client.get(PATH, params={"portfolio_id": 1}).json() == routes.unavailable()


def test_store_or_registry_failure_is_unavailable_not_an_error(caplog):
    client, _, _, _ = _client(store=FakeStore(fail=True))
    response = client.get(PATH, params={"portfolio_id": 1})
    assert response.status_code == 200 and response.json() == routes.unavailable()
    assert "db down" not in caplog.text

    def broken():
        raise ImportError("rules")

    store = FakeStore()
    app = FastAPI()
    router = APIRouter()
    register_auditor_user_routes(router, FakeRepo(), store_getter=lambda: store, rules_loader=broken, now=lambda: NOW)
    app.include_router(router, prefix="/api")
    app.dependency_overrides[require_auth] = lambda: AuthContext(user_id="user-1", org_id=None, email=None, claims={})
    assert TestClient(app).get(PATH, params={"portfolio_id": 1}).json() == routes.unavailable()


def test_real_registry_titles_have_no_rule_ids():
    rules = load_rules()
    assert rules, "registro vuoto"
    rows = [_row(1, rule.id, "pass" if i % 3 else "fail") for i, rule in enumerate(rules)]
    body = build_summary({"run": {"finished_at": FINISHED}, "rows": rows}, rules, now=NOW)
    assert body["available"] is True
    assert body["checks_passed"] + body["checks_in_review"] == len(rules)
    _assert_no_internals(body)
    assert {a["label"] for a in body["areas"]} <= set(AREAS.values())


def test_registered_on_the_main_app(monkeypatch):
    import app.main as api_main

    store = FakeStore()
    monkeypatch.setattr(api_main, "repo", FakeRepo(owned={"dev-user": {1, 2}}))
    monkeypatch.setattr(api_main, "auditor_nightly", SimpleNamespace(store=store))
    monkeypatch.setattr(routes, "_utcnow", lambda: NOW)
    client = TestClient(api_main.app)
    assert PATH in api_main.app.openapi()["paths"]
    response = client.get(PATH, params={"portfolio_ids": "1,2"})
    assert response.status_code == 200, response.text
    assert store.calls == [[1, 2]]
    assert client.get(PATH, params={"portfolio_id": 9}).status_code == 404
