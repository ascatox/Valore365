"""Doctor 2.0 metrics, snapshot and PRD golden fixtures."""

from datetime import UTC, date, datetime

import pytest

from app.models import Position
from app.services.doctor_policy import (
    METRIC_CODES,
    build_evaluation_response,
    build_scope,
    build_snapshot,
    compute_metrics,
    evaluate_policy,
    normalize_scope_ids,
    policy_asset_class,
    scope_fingerprint,
    scope_type,
    snapshot_from_holdings,
)
from app.services.doctor_policy.scope import ScopeError
from app.services.portfolio_doctor import AnalyzedHolding, analyze_portfolio_health

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _h(asset_id, symbol, name, asset_type, value, ccy="USD", isin=None, **extra):
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type,
        quote_currency=ccy, market_value=float(value), weight_pct=0.0, isin=isin, **extra,
    )


def _snap(holdings, **kwargs):
    kwargs.setdefault("price_as_of", {h.asset_id: "2026-11-03" for h in holdings})
    return snapshot_from_holdings(holdings, portfolio_ids=kwargs.pop("portfolio_ids", [1]), **kwargs)


def _rule(rule_id, metric_code, operator="max", **values):
    return {"rule_id": rule_id, "metric_code": metric_code, "operator": operator, **values}


def _one(doc_rule, snapshot, metrics=None):
    metrics = metrics or compute_metrics(snapshot)
    return evaluate_policy({"rules": [doc_rule]}, metrics, snapshot, now=NOW).results[0]


VWCE = ("VWCE", "Vanguard FTSE All-World UCITS ETF", "etf")
AGGH = ("AGGH", "iShares Core Global Aggregate Bond UCITS ETF", "etf")
SGLD = ("SGLD", "Invesco Physical Gold ETC", "etf")


# -- scope ------------------------------------------------------------------


def test_scope_fingerprint_type_dedup_limits():
    assert scope_fingerprint([26, 19, 26]) == "p:19,26"
    assert scope_type([19, 19]) == "single"
    assert scope_type([19, 26]) == "aggregate"
    assert normalize_scope_ids(["5", 3]) == [3, 5]
    assert build_scope([26, 19]).model_dump() == {"portfolio_ids": [19, 26], "scope_type": "aggregate", "fingerprint": "p:19,26"}
    for bad in ([], [0], [-1], [True], ["x"], list(range(1, 22))):
        with pytest.raises(ScopeError):
            normalize_scope_ids(bad)
    assert len(normalize_scope_ids(list(range(1, 21)))) == 20


# -- registry ---------------------------------------------------------------


def test_registry_has_the_8_mvp_metrics_in_pct():
    assert METRIC_CODES == (
        "equity_weight_pct", "bond_weight_pct", "gold_weight_pct", "max_single_position_pct",
        "top3_positions_pct", "usa_exposure_pct", "weighted_ter_pct", "etf_overlap_pct",
    )
    metrics = compute_metrics(_snap([_h(1, *VWCE, 100, "EUR")]))
    assert set(metrics) == set(METRIC_CODES)
    assert all(m.unit == "pct" for m in metrics.values())


# -- golden: asset classes 60/35/5 ---------------------------------------------


def test_golden_asset_classes_60_35_5_and_cash_excluded():
    snap = _snap([
        _h(1, *VWCE, 6000, "EUR"),
        _h(2, *AGGH, 3500, "EUR"),
        _h(3, *SGLD, 500, "EUR"),
        _h(4, "CASH", "Liquidità", "cash", 5000, "EUR"),
    ], cash_value=2000)
    m = compute_metrics(snap)
    assert snap.invested_value == 10000
    assert m["equity_weight_pct"].value == pytest.approx(60.0)
    assert m["bond_weight_pct"].value == pytest.approx(35.0)
    assert m["gold_weight_pct"].value == pytest.approx(5.0)
    assert all(m[c].coverage_pct == 100.0 and m[c].quality == "ok" for c in ("equity_weight_pct", "bond_weight_pct"))
    assert m["equity_weight_pct"].denominator_value == 10000


def test_precious_metals_count_with_gold_and_miners_do_not():
    silver = _h(1, "PHAG", "WisdomTree Physical Silver ETC", "etf", 50)
    miners = _h(2, "GDX", "VanEck Gold Miners UCITS ETF", "etf", 50)
    assert policy_asset_class(silver) == "gold"
    assert policy_asset_class(miners) == "equity"
    m = compute_metrics(_snap([silver, miners]))
    assert m["gold_weight_pct"].value == pytest.approx(50.0)


def test_unknown_class_gives_bounds_not_zero():
    snap = _snap([_h(1, *VWCE, 6000, "EUR"), _h(2, "XYZ1", "XYZ1", "fund", 4000, "EUR")])
    m = compute_metrics(snap)["equity_weight_pct"]
    assert (m.lower, m.upper, m.coverage_pct, m.quality) == (pytest.approx(60.0), pytest.approx(100.0), pytest.approx(60.0), "partial")
    bond = compute_metrics(snap)["bond_weight_pct"]
    assert bond.lower == 0 and bond.upper == pytest.approx(40.0)


def test_equity_70_vs_max_65_fails_breach_5():
    snap = _snap([_h(1, *VWCE, 7000, "EUR"), _h(2, *AGGH, 3000, "EUR")])
    result = _one(_rule("eq", "equity_weight_pct", max_value=65), snap)
    assert result.status == "FAIL"
    assert result.breach_amount == pytest.approx(5.0)


# -- golden: concentration --------------------------------------------------


def test_single_security_46_6_vs_max_35_exact_reason():
    snap = _snap([
        _h(1, "VWRA", "Vanguard FTSE All-World UCITS ETF (USD) Accumulating", "etf", 4660, "USD", "IE00BK5BQT80"),
        _h(2, *AGGH, 3340, "EUR"),
        _h(3, *SGLD, 2000, "EUR"),
    ])
    result = _one(_rule("max-single", "max_single_position_pct", max_value=35), snap)
    assert result.status == "FAIL"
    assert result.breach_amount == pytest.approx(11.6)
    assert result.reason == "VWRA 46,6%: supera il tuo limite 35% di 11,6 punti percentuali"
    assert result.evidence.contributors[0].isin == "IE00BK5BQT80"


def test_same_isin_on_two_listings_is_one_security():
    snap = _snap([
        _h(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 3000, "EUR", "IE00BK5BQT80"),
        _h(2, "VWCE.DE", "Vanguard FTSE All-World UCITS ETF", "etf", 2000, "EUR", "IE00BK5BQT80"),
        _h(3, *AGGH, 2500, "EUR", "IE00BDBRDM35"),
        _h(4, *SGLD, 2500, "EUR"),
    ])
    m = compute_metrics(snap)
    assert m["max_single_position_pct"].value == pytest.approx(50.0)
    assert m["top3_positions_pct"].value == pytest.approx(100.0)
    assert any("VWCE/VWCE.DE" in note for note in m["max_single_position_pct"].notes)
    # One fund with itself is not an overlap pair.
    assert m["etf_overlap_pct"].value < 100


def test_same_security_in_two_portfolios_aggregated_once():
    """The aggregate snapshot reads positions with get_positions_multi (one
    position per asset); a duplicate holding row is merged as well."""
    positions = [
        _position(1, "VWRA", "Vanguard FTSE All-World UCITS ETF", 3000),
        _position(2, "AGGH", "iShares Core Global Aggregate Bond UCITS ETF", 4000),
    ]
    repo = _FakeRepo(positions_multi=positions + [_position(1, "VWRA", "Vanguard FTSE All-World UCITS ETF", 3000)])
    snap = build_snapshot(repo, [26, 19], "user")
    assert snap.portfolio_ids == [19, 26]
    assert repo.calls == [("multi", [19, 26])]
    assert len(snap.holdings) == 2
    m = compute_metrics(snap)
    assert m["max_single_position_pct"].value == pytest.approx(60.0)
    assert m["max_single_position_pct"].contributors[0]["symbol"] == "VWRA"


# -- golden: USA bounds -------------------------------------------------------


def test_usa_known_35_unknown_30_max_60_is_unknown():
    snap = _snap([
        _h(1, "CSPX", "iShares Core S&P 500 UCITS ETF", "etf", 3500, "USD"),
        _h(2, "MEUD", "Amundi Stoxx Europe 600 UCITS ETF", "etf", 3500, "EUR"),
        _h(3, "ZZZF", "Fondo Alfa Accumulazione", "etf", 3000, "EUR"),
    ])
    m = compute_metrics(snap)["usa_exposure_pct"]
    assert m.lower == pytest.approx(35.0)
    assert m.upper == pytest.approx(65.0)
    assert m.coverage_pct == pytest.approx(70.0)
    assert m.quality == "partial"
    result = _one(_rule("usa", "usa_exposure_pct", max_value=60), snap)
    assert result.status == "UNKNOWN"
    assert result.reason.startswith("Non possiamo verificare il limite USA: copertura insufficiente")
    assert (result.actual_lower, result.actual_upper) == (pytest.approx(35.0), pytest.approx(65.0))


def test_usa_known_50_unclassified_15_max_60_is_unknown_not_pass():
    snap = _snap([
        _h(1, "CSPX", "iShares Core S&P 500 UCITS ETF", "etf", 5000, "USD"),
        _h(2, "MEUD", "Amundi Stoxx Europe 600 UCITS ETF", "etf", 3500, "EUR"),
        _h(3, "ZZZF", "Fondo Alfa Accumulazione", "etf", 1500, "EUR"),
    ])
    m = compute_metrics(snap)["usa_exposure_pct"]
    assert (m.lower, m.upper, m.coverage_pct) == (pytest.approx(50.0), pytest.approx(65.0), pytest.approx(85.0))
    result = _one(_rule("usa", "usa_exposure_pct", max_value=60), snap)
    assert result.status == "UNKNOWN"
    assert "tra 50,0% e 65,0%" in result.reason


def test_usa_uses_country_weights_from_repo_with_explicit_remainder():
    class Repo:
        def get_etf_enrichment_bulk(self, ids):
            return {1: {"country_weights": [{"name": "United States", "percentage": 60.0}, {"name": "Japan", "percentage": 20.0}]}}

    snap = _snap([_h(1, *VWCE, 10000, "EUR")])
    m = compute_metrics(snap, repo=Repo())["usa_exposure_pct"]
    assert (m.lower, m.upper, m.coverage_pct, m.source) == (pytest.approx(60.0), pytest.approx(80.0), pytest.approx(80.0), "geographic_lookthrough")


# -- golden: TER coverage ---------------------------------------------------------


def test_ter_covered_60_pct_with_min_coverage_80_is_unknown():
    snap = _snap([
        _h(1, "CSPX", "iShares Core S&P 500 UCITS ETF", "etf", 6000, "USD"),  # inferred 0.07 (CORE)
        _h(2, "ZZZF", "Fondo Alfa", "fund", 4000, "EUR"),  # no TER
    ])
    m = compute_metrics(snap)["weighted_ter_pct"]
    assert m.coverage_pct == pytest.approx(60.0)
    assert m.value == pytest.approx(0.07)
    assert m.quality == "partial"
    assert m.source == "ter_inferred"
    result = _one(_rule("ter", "weighted_ter_pct", max_value=0.3, min_coverage_pct=80), snap)
    assert result.status == "UNKNOWN"
    assert "copertura insufficiente" in result.reason


def test_ter_from_repo_registry():
    class Meta:
        expense_ratio = None
        raw_info = None

    class Repo:
        def get_etf_enrichment_bulk(self, ids):
            return {1: {"ter": 0.22}}

        def get_asset_metadata_bulk(self, ids):
            return {}

    snap = _snap([_h(1, *VWCE, 10000, "EUR")])
    m = compute_metrics(snap, repo=Repo())["weighted_ter_pct"]
    assert m.value == pytest.approx(0.22) and m.coverage_pct == 100.0 and m.source == "ter_registry"


def test_no_ter_at_all_is_missing_not_zero():
    m = compute_metrics(_snap([_h(1, "ZZZF", "Fondo Alfa", "fund", 100, "EUR")]))["weighted_ter_pct"]
    assert m.value is None and m.quality == "missing"


# -- stale ---------------------------------------------------------------------


def test_stale_quotes_make_rules_unknown_not_pass():
    holdings = [_h(1, *VWCE, 6000, "EUR"), _h(2, *AGGH, 4000, "EUR")]
    fresh = _snap(holdings)
    stale = _snap(holdings, stale_asset_ids=[2])
    rule = _rule("eq", "equity_weight_pct", max_value=65)
    assert _one(rule, fresh).status == "PASS"
    result = _one(rule, stale)
    assert result.status == "UNKNOWN"
    assert result.quality == "stale"
    assert stale.data_quality["status"] == "stale"
    assert stale.data_quality["stale_symbols"] == ["AGGH"]


# -- zero denominator / empty -------------------------------------------------


def test_zero_denominator_only_cash():
    snap = _snap([_h(1, "CASH", "Liquidità", "cash", 1000, "EUR")])
    assert snap.is_empty
    metrics = compute_metrics(snap)
    assert all(m.value is None and m.quality == "missing" for m in metrics.values())
    response = build_evaluation_response({"rules": [_rule("eq", "equity_weight_pct", max_value=65)]}, snap, metrics, now=NOW)
    assert response.status == "empty_portfolio"
    assert response.results[0].status == "NOT_APPLICABLE"


# -- snapshot -------------------------------------------------------------------


def test_snapshot_id_is_deterministic_and_sensitive():
    holdings = [_h(1, *VWCE, 6000, "EUR"), _h(2, *AGGH, 4000, "EUR")]
    a = _snap(holdings)
    b = _snap(list(reversed(holdings)))
    assert a.snapshot_id == b.snapshot_id
    assert len(a.snapshot_id) == 16
    assert _snap([_h(1, *VWCE, 6001, "EUR"), _h(2, *AGGH, 4000, "EUR")]).snapshot_id != a.snapshot_id
    assert _snap(holdings, price_as_of={1: "2026-11-02", 2: "2026-11-03"}).snapshot_id != a.snapshot_id
    # The caller's holdings are not mutated.
    assert holdings[0].weight_pct == 0.0


def test_compute_metrics_does_not_mutate_snapshot():
    snap = _snap([_h(1, *VWCE, 6000, "EUR"), _h(2, *AGGH, 4000, "EUR")])
    before = snap.snapshot_id
    compute_metrics(snap)
    assert snap.snapshot_id == before


def _position(asset_id, symbol, name, value, *, stale=False, price_date=date(2026, 11, 3), fallback=None):
    return Position(
        asset_id=asset_id, symbol=symbol, name=name, asset_type="etf", quantity=10, avg_cost=1,
        market_price=value / 10, market_value=value, unrealized_pl=0, unrealized_pl_pct=0, weight=0,
        price_stale=stale, price_date=price_date, price_fallback=fallback,
    )


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _Conn:
    def execute(self, statement, params=None):
        sql = str(statement)
        if "from assets" in sql:
            return _Result([
                {"id": aid, "asset_type": "etf", "quote_currency": "EUR", "isin": None, "category": None,
                 "index_tracked": None, "investment_focus": None, "enrichment_name": None}
                for aid in params["asset_ids"]
            ])
        return _Result([])


class _Begin:
    def __enter__(self):
        return _Conn()

    def __exit__(self, *exc):
        return False


class _Engine:
    def begin(self):
        return _Begin()


class _Scope:
    def __init__(self, ids):
        self.portfolio_ids = tuple(ids)
        self.base_currency = "EUR"


class _FakeRepo:
    engine = _Engine()

    def __init__(self, positions=None, positions_multi=None, sync=None):
        self.positions = positions or []
        self.positions_multi = positions_multi or []
        self.sync = sync
        self.calls = []

    def resolve_portfolio_scope(self, ids, user_id):
        ids = list(ids)
        if 999 in ids:
            raise ValueError("Portfolio non trovato")
        return _Scope(ids)

    def get_positions(self, portfolio_id, user_id):
        self.calls.append(("single", portfolio_id))
        return self.positions

    def get_positions_multi(self, ids, user_id):
        self.calls.append(("multi", list(ids)))
        return self.positions_multi

    def get_market_data_sync_overview(self):
        if self.sync is None:
            raise RuntimeError("no sync table")
        return self.sync

    def get_etf_enrichment_bulk(self, ids):
        return {}

    def get_asset_metadata_bulk(self, ids):
        return {}


def test_build_snapshot_single_portfolio_freshness():
    repo = _FakeRepo(
        positions=[
            _position(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", 6000),
            _position(2, "AGGH", "iShares Core Global Aggregate Bond UCITS ETF", 3000, stale=True, price_date=date(2026, 10, 20)),
            _position(3, "ZZZF", "Fondo Alfa", 1000, price_date=None, fallback="avg_cost"),
        ],
        sync={"last_success": {"finished_at": datetime(2026, 11, 4, 6, tzinfo=UTC)}, "last_run": {"status": "success", "finished_at": datetime(2026, 11, 4, 6, tzinfo=UTC)}},
    )
    snap = build_snapshot(repo, [5], "user")
    assert repo.calls == [("single", 5)]
    assert snap.base_currency == "EUR"
    assert snap.invested_value == 10000
    assert snap.stale_symbols == ["AGGH"]
    assert snap.missing_price_symbols == ["ZZZF"]
    assert snap.quote_as_of == "2026-10-20"
    dq = snap.data_quality
    assert dq["status"] == "stale"
    assert dq["last_sync_status"] == "success"
    assert "AGGH" in dq["note"]
    response = build_evaluation_response({"rules": [_rule("eq", "equity_weight_pct", max_value=65)]}, snap, repo=repo, now=NOW)
    assert response.results[0].status == "UNKNOWN"
    assert response.data_quality.status == "stale"


def test_build_snapshot_rejects_not_owned_and_invalid_scope():
    with pytest.raises(ValueError):
        build_snapshot(_FakeRepo(), [1, 999], "user")
    with pytest.raises(ScopeError):
        build_snapshot(_FakeRepo(), [], "user")


# -- Health score unchanged & coexistence (PRD example B) --------------------------


class _HealthConn(_Conn):
    def __init__(self, classes):
        self.classes = classes

    def execute(self, statement, params=None):
        sql = str(statement)
        if "from assets" in sql:
            return _Result([
                {"id": aid, "asset_type": self.classes[aid], "quote_currency": "EUR", "isin": None, "category": None,
                 "index_tracked": None, "investment_focus": None, "enrichment_name": None}
                for aid in params["asset_ids"]
            ])
        return _Result([])  # no price history: volatility None


class _HealthRepo(_FakeRepo):
    def __init__(self, positions, classes):
        super().__init__(positions=positions)
        conn = _HealthConn(classes)

        class Begin:
            def __enter__(self_inner):
                return conn

            def __exit__(self_inner, *exc):
                return False

        class Engine:
            def begin(self_inner):
                return Begin()

        self.engine = Engine()


def _example_b_repo():
    positions = [
        _position(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", 2500),
        _position(2, "AGGH", "iShares Core Global Aggregate Bond UCITS ETF", 2500),
        _position(3, "MEUD", "Amundi Stoxx Europe 600 UCITS ETF", 2000),
        _position(4, "EIMI", "iShares Core MSCI Emerging Markets IMI UCITS ETF", 1500),
        _position(5, "SGLD", "Invesco Physical Gold ETC", 1500),
    ]
    total = sum(p.market_value for p in positions)
    for p in positions:
        p.weight = round(p.market_value / total * 100, 2)
    return _HealthRepo(positions, {1: "etf", 2: "etf", 3: "etf", 4: "etf", 5: "etf"})


def test_health_score_unchanged_by_policy_evaluation():
    repo = _example_b_repo()
    before = analyze_portfolio_health(repo, 1, "user").model_dump()
    snap = build_snapshot(repo, [1], "user")
    metrics = compute_metrics(snap, repo=repo)
    build_evaluation_response({"rules": [_rule("ms", "max_single_position_pct", max_value=10)]}, snap, metrics, repo=repo, now=NOW)
    after = analyze_portfolio_health(repo, 1, "user").model_dump()
    assert before == after


def test_example_b_health_100_but_policy_violated_coexist():
    repo = _example_b_repo()
    health = analyze_portfolio_health(repo, 1, "user")
    assert health.score == 100
    snap = build_snapshot(repo, [1], "user")
    response = build_evaluation_response(
        {"rules": [_rule("eq-max", "equity_weight_pct", max_value=50, severity="high")]},
        snap, repo=repo, now=NOW,
    )
    result = response.results[0]
    assert result.status == "FAIL"
    assert result.actual == pytest.approx(60.0)
    assert result.breach_amount == pytest.approx(10.0)
    # The Health response is the standard one (no policy fields leak into it).
    assert "policy" not in health.model_dump()


# -- PRD §6: metric metadata ---------------------------------------------------


REQUIRED_METRIC_FIELDS = (
    "value", "unit", "source", "quote_as_of", "calculated_at", "coverage_pct", "methodology_version", "quality",
)


@pytest.mark.parametrize("holdings", [
    [_h(1, *VWCE, 6000, "EUR"), _h(2, *AGGH, 4000, "EUR")],
    [],  # empty portfolio: metrics missing, metadata still present
])
def test_every_metric_exposes_prd_metadata(holdings):
    from app.schemas.doctor_policy import MetricValueRead
    from app.services.doctor_policy.metrics import METHODOLOGY_VERSION

    snap = _snap(holdings, price_as_of={1: "2026-11-02", 2: "2026-11-03"} if holdings else {})
    metrics = compute_metrics(snap, now=NOW)
    assert set(metrics) == set(METRIC_CODES)
    for metric in metrics.values():
        data = MetricValueRead(**metric.to_dict()).model_dump()
        assert set(REQUIRED_METRIC_FIELDS) <= set(data)
        assert data["calculated_at"] == NOW.isoformat()
        assert data["methodology_version"] == METHODOLOGY_VERSION
        assert data["quote_as_of"] == snap.quote_as_of
        assert data["unit"] == "pct" and data["source"]
    if holdings:
        assert snap.quote_as_of == "2026-11-02"


def test_scenario_side_metrics_carry_metadata():
    from app.services.doctor_policy import scenario

    snap = _snap([_h(1, *VWCE, 6000, "EUR"), _h(2, *AGGH, 4000, "EUR")])
    result = scenario.preview_scenario(
        snap, {"portfolio_ids": [1], "mode": "new_cash_only", "new_cash": 1000}, policy_document=None, now=NOW,
    )
    for side in (result.before, result.after):
        for metric in side.metrics.values():
            assert metric.calculated_at == NOW.isoformat()
            assert metric.methodology_version and metric.quote_as_of == "2026-11-03"
