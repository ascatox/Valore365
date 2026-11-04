"""Scenario Lab invariants with seeded random portfolios/scenarios (no hypothesis).

Every seed is fixed: a failure is reproducible by its iteration number.
"""

from __future__ import annotations

import inspect
import random
from datetime import UTC, datetime

import pytest

from app.services.doctor_policy import METHODOLOGY_VERSION, scenario as scenario_module, snapshot_from_holdings
from app.services.doctor_policy.errors import InvalidRequest
from app.services.doctor_policy.scenario import compare_scenarios, preview_scenario
from app.services.portfolio_doctor import AnalyzedHolding

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
ITERATIONS = 300

TEMPLATES = [
    ("Vanguard FTSE All-World UCITS ETF", "etf"),
    ("iShares Core S&P 500 UCITS ETF", "etf"),
    ("iShares Core Global Aggregate Bond UCITS ETF", "etf"),
    ("Xtrackers II EUR Overnight Rate Swap UCITS ETF", "etf"),
    ("Invesco Physical Gold ETC", "etf"),
    ("Apple Inc", "stock"),
    ("Mystery Holdings Plc", "fund"),
    ("iShares Core MSCI EM IMI UCITS ETF", "etf"),
]


def random_holdings(rng: random.Random) -> list[AnalyzedHolding]:
    n = rng.randint(1, 8)
    holdings = []
    for i in range(n):
        name, kind = rng.choice(TEMPLATES)
        # Sometimes two listings of the same ISIN (canonical security aggregation).
        isin = f"IE{rng.randint(0, 4 if rng.random() < 0.3 else 10**9):010d}"
        holdings.append(AnalyzedHolding(
            asset_id=i + 1, symbol=f"S{i + 1}", name=name, asset_type=kind, quote_currency="EUR",
            market_value=round(rng.uniform(100, 500_000), 2), weight_pct=0.0, isin=isin,
        ))
    return holdings


def random_doc(rng: random.Random) -> dict | None:
    if rng.random() < 0.15:
        return None
    rules = [{"rule_id": "single", "metric_code": "max_single_position_pct", "operator": "max",
              "max_value": rng.choice([20, 30, 35, 50, 70])}]
    if rng.random() < 0.6:
        rules.append({"rule_id": "equity", "metric_code": "equity_weight_pct", "operator": "range",
                      "min_value": 30, "max_value": 80})
    if rng.random() < 0.4:
        rules.append({"rule_id": "top3", "metric_code": "top3_positions_pct", "operator": "max", "max_value": 90})
    return {"schema_version": 1, "rules": rules}


def random_request(rng: random.Random, holdings: list[AnalyzedHolding]) -> dict:
    mode = rng.choice(["manual", "new_cash_only", "rebalance"])
    fee = {"pct": rng.choice([0, 0, 0.1, 0.5]), "fixed": rng.choice([0, 0, 1, 5])}
    constraints = {
        "no_sell": rng.random() < 0.3,
        "keep_equity_total": rng.random() < 0.2,
        "use_cash_balance": rng.random() < 0.2,
        "max_turnover_pct": rng.choice([None, None, 5, 20, 60]),
    }
    req = {"mode": mode, "fee_model": fee, "constraints": constraints,
           "new_cash": rng.choice([0, 0, round(rng.uniform(0, 300_000), 2)])}
    ids = [h.asset_id for h in holdings]
    if mode == "manual":
        ops = []
        for _ in range(rng.randint(1, 6)):
            h = rng.choice(holdings)
            action = rng.choice(["buy", "sell"])
            amount = round(rng.uniform(1, h.market_value * (1.2 if action == "sell" else 0.5)), 2)
            ops.append({"symbol" if rng.random() < 0.5 else "asset_id": h.symbol if rng.random() < 0.5 else h.asset_id,
                        "action": action, "amount": amount})
        # keep only well-typed identifiers
        req["operations"] = [
            {**op, "asset_id": op["asset_id"]} if isinstance(op.get("asset_id"), int)
            else {"symbol": str(op.get("symbol", op.get("asset_id"))), "action": op["action"], "amount": op["amount"]}
            for op in ops
        ]
    elif mode == "new_cash_only":
        if rng.random() < 0.4:
            listed = rng.sample(ids, rng.randint(1, len(ids)))
            req["target_weights"] = {str(a): rng.choice([20, 30, 35, 50, 100]) / len(listed) * 1.0 for a in listed}
    else:
        listed = rng.sample(ids, rng.randint(1, len(ids)))
        raw = [rng.uniform(0, 1) for _ in listed]
        total = sum(raw) or 1.0
        scale = 100.0 if len(listed) == len(ids) else rng.uniform(10, 95)
        weights = [r / total * scale for r in raw]
        weights[-1] = max(0.0, scale - sum(weights[:-1]))
        req["target_weights"] = {str(a): min(100.0, w) for a, w in zip(listed, weights)}
    return req


def build(rng):
    holdings = random_holdings(rng)
    cash = rng.choice([0.0, round(rng.uniform(0, 50_000), 2)])
    snap = snapshot_from_holdings(
        holdings, portfolio_ids=[1], cash_value=cash, price_as_of={h.asset_id: "2026-11-03" for h in holdings},
    )
    return holdings, snap


def simulate(snap, req, doc):
    try:
        return preview_scenario(snap, req, policy_document=doc, now=NOW)
    except InvalidRequest:
        return None


def check_invariants(result, req, snap):
    tol = 1e-7 * max(1.0, result.total_before) + 1e-6
    assert result.methodology_version == METHODOLOGY_VERSION
    assert result.snapshot_id == snap.snapshot_id
    assert result.before.total_value == pytest.approx(snap.invested_value + snap.cash_value)
    if not result.feasible:
        assert result.after is None and result.changes == [] and result.total_after is None
        assert result.infeasible_reason and result.infeasible_code
        return
    after = result.after
    # capital conservation: only external cash and costs change the total
    assert abs(result.total_after - (result.total_before + result.cash_in - result.costs.total)) <= tol
    if result.cash_in == 0 and result.costs.total == 0:
        assert abs(result.total_after - result.total_before) <= tol
    assert abs(after.invested_value + after.cash_value - result.total_after) <= tol
    # no negative cash, no short
    assert after.cash_value >= -1e-6
    for c in result.changes:
        assert c.after_value >= 0
        assert c.delta_value >= -c.before_value - 1e-6
    # constraints
    if req["mode"] == "new_cash_only" or req["constraints"]["no_sell"]:
        assert all(c.delta_value >= -1e-6 for c in result.changes)
    if req["constraints"]["keep_equity_total"]:
        b, a = result.before.metrics["equity_weight_pct"], after.metrics["equity_weight_pct"]
        assert (b.value is None) == (a.value is None)
        if b.value is not None:
            assert a.value == pytest.approx(b.value, abs=1e-6)
    limit = req["constraints"]["max_turnover_pct"]
    if limit is not None and result.turnover_pct is not None:
        assert result.turnover_pct <= limit + 1e-6
    if req["mode"] == "rebalance":
        weights = {c.asset_id: c.after_weight for c in result.changes}
        for key, target in req["target_weights"].items():
            assert weights[int(key)] == pytest.approx(target, abs=1e-6)
    # same methodology and metrics before/after, never a recycled volatility
    assert set(after.metrics) == set(result.before.metrics)
    for r in after.rule_results + result.before.rule_results:
        assert r.evidence.methodology_version == METHODOLOGY_VERSION
    assert after.volatility.value is None


def test_random_scenarios_respect_invariants():
    feasible = infeasible = 0
    for i in range(ITERATIONS):
        rng = random.Random(1000 + i)
        holdings, snap = build(rng)
        doc = random_doc(rng)
        req = random_request(rng, holdings)
        before_values = [(h.asset_id, h.market_value) for h in snap.holdings]
        result = simulate(snap, req, doc)
        # the snapshot is never mutated
        assert [(h.asset_id, h.market_value) for h in snap.holdings] == before_values, i
        if result is None:
            continue
        try:
            check_invariants(result, req, snap)
        except AssertionError as exc:  # pragma: no cover - diagnostic
            raise AssertionError(f"iteration {i}: {req}") from exc
        feasible += result.feasible
        infeasible += not result.feasible
    # the generator explores both outcomes
    assert feasible > 50 and infeasible > 20


def test_required_new_cash_is_sufficient():
    checked = 0
    for i in range(ITERATIONS):
        rng = random.Random(5000 + i)
        holdings, snap = build(rng)
        doc = random_doc(rng)
        req = random_request(rng, holdings)
        result = simulate(snap, req, doc)
        if result is None or result.feasible or result.required_new_cash is None:
            continue
        if result.infeasible_code not in ("insufficient_cash", "no_sell"):
            continue
        retry = simulate(snap, {**req, "new_cash": result.required_new_cash}, doc)
        assert retry is not None
        # More cash can still hit another constraint (turnover, capacity), never the cash one.
        assert retry.feasible or retry.infeasible_code not in ("insufficient_cash", "no_sell"), (i, req, retry.infeasible_reason)
        checked += 1
    assert checked > 10


def test_reproducible_for_identical_snapshot():
    for i in range(60):
        rng = random.Random(9000 + i)
        holdings, snap = build(rng)
        doc = random_doc(rng)
        req = random_request(rng, holdings)
        a, b = simulate(snap, req, doc), simulate(snap, req, doc)
        if a is None:
            assert b is None
            continue
        assert a.model_dump() == b.model_dump()
        # and on an identical snapshot rebuilt from the same holdings
        _h, snap2 = build(random.Random(9000 + i))
        assert snap2.snapshot_id == snap.snapshot_id
        assert simulate(snap2, req, doc).model_dump() == a.model_dump()


def test_aggregate_scope_invariant_under_permutation_of_portfolio_ids():
    for i in range(60):
        rng = random.Random(12000 + i)
        holdings, _ = build(rng)
        doc = random_doc(rng)
        req = random_request(rng, holdings)
        ids = rng.sample(range(1, 30), rng.randint(2, 5))
        outputs = []
        for perm in range(3):
            prng = random.Random(perm)
            pids = ids[:]
            prng.shuffle(pids)
            hs = holdings[:]
            prng.shuffle(hs)
            snap = snapshot_from_holdings(
                hs, portfolio_ids=pids, price_as_of={h.asset_id: "2026-11-03" for h in hs},
            )
            out = simulate(snap, req, doc)
            outputs.append(None if out is None else out.model_dump())
        assert outputs[0] == outputs[1] == outputs[2], i
        if outputs[0] is not None:
            assert outputs[0]["scope"]["scope_type"] == "aggregate"
            assert any("Scope aggregato" in w for w in outputs[0]["warnings"])


class _ReadOnlyRepo:
    """Only the reads used by the metrics; any other attribute (engine, writes) fails."""

    def __init__(self):
        self.calls = []

    def get_etf_enrichment_bulk(self, ids):
        self.calls.append("get_etf_enrichment_bulk")
        return {}

    def get_asset_metadata_bulk(self, ids):
        self.calls.append("get_asset_metadata_bulk")
        return {}

    def __getattr__(self, name):
        raise AssertionError(f"Scenario Lab touched repo.{name}")


def test_no_db_writes_with_repository():
    rng = random.Random(42)
    for i in range(40):
        holdings, snap = build(rng)
        repo = _ReadOnlyRepo()
        req = random_request(rng, holdings)
        try:
            preview_scenario(snap, req, policy_document=random_doc(rng), repo=repo, now=NOW)
            compare_scenarios(snap, [req, {"mode": "new_cash_only", "new_cash": 1000}], policy_document=None, repo=repo, now=NOW)
        except InvalidRequest:
            continue
        assert set(repo.calls) <= {"get_etf_enrichment_bulk", "get_asset_metadata_bulk"}


def test_scenario_module_has_no_persistence_code():
    source = inspect.getsource(scenario_module).lower()
    for forbidden in (".engine", "execute(", "insert ", "update ", "delete from", "commit(", "store."):
        assert forbidden not in source, forbidden
