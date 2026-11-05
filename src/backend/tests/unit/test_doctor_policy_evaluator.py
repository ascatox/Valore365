"""Doctor 2.0 evaluator: statuses, bounds, epsilon, near limit, ordering, texts."""

from datetime import UTC, datetime

import pytest

from app.services.doctor_policy import (
    MetricValue,
    build_evaluation_response,
    compute_metrics,
    evaluate_policy,
    snapshot_from_holdings,
)
from app.services.portfolio_doctor import AnalyzedHolding

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _h(asset_id, symbol, name, asset_type, value, ccy="USD", isin=None):
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type,
        quote_currency=ccy, market_value=float(value), weight_pct=0.0, isin=isin,
    )


def _snapshot(holdings=None, **kwargs):
    holdings = holdings or [
        _h(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 6000, "EUR"),
        _h(2, "AGGH", "iShares Core Global Aggregate Bond UCITS ETF", "etf", 4000, "EUR"),
    ]
    kwargs.setdefault("price_as_of", {h.asset_id: "2026-11-03" for h in holdings})
    return snapshot_from_holdings(holdings, portfolio_ids=[7], **kwargs)


def _metric(code, value, lower=None, upper=None, coverage=100.0, quality="ok"):
    return MetricValue(
        code=code, value=value,
        lower=value if lower is None else lower,
        upper=value if upper is None else upper,
        coverage_pct=coverage, quality=quality, source="test", denominator="test", denominator_value=100.0,
    )


def _rule(**overrides):
    rule = {"rule_id": "r1", "metric_code": "equity_weight_pct", "operator": "max", "max_value": 65.0}
    rule.update(overrides)
    return rule


def _eval(rule, metric, snapshot=None):
    snapshot = snapshot or _snapshot()
    result = evaluate_policy({"rules": [rule]}, {metric.code: metric} if metric else {}, snapshot, now=NOW)
    return result.results[0]


# -- operators and inclusive bounds -----------------------------------------


@pytest.mark.parametrize("value, status", [(64.9, "PASS"), (65.0, "PASS"), (65.0 + 1e-10, "PASS"), (65.0 + 1e-6, "FAIL"), (70.0, "FAIL")])
def test_max_is_inclusive_with_epsilon(value, status):
    assert _eval(_rule(warning_margin=0), _metric("equity_weight_pct", value)).status == status


@pytest.mark.parametrize("value, status", [(30.0, "PASS"), (30.0 - 1e-10, "PASS"), (29.99, "FAIL"), (50.0, "PASS")])
def test_min_is_inclusive(value, status):
    rule = _rule(metric_code="bond_weight_pct", operator="min", max_value=None, min_value=30.0, warning_margin=0)
    assert _eval(rule, _metric("bond_weight_pct", value)).status == status


@pytest.mark.parametrize("value, status, breach", [(50.0, "PASS", None), (70.0, "PASS", None), (45.0, "FAIL", 5.0), (72.5, "FAIL", 2.5)])
def test_range(value, status, breach):
    rule = _rule(operator="range", min_value=50.0, max_value=70.0, warning_margin=0)
    result = _eval(rule, _metric("equity_weight_pct", value))
    assert result.status == status
    assert result.breach_amount == breach


def test_compare_on_unrounded_value():
    # 65.04 shows as 65,0% with precision 1 but is above the limit 65.
    result = _eval(_rule(), _metric("equity_weight_pct", 65.04))
    assert result.status == "FAIL"
    assert result.breach_amount == pytest.approx(0.04)
    assert "65,0%" in result.reason


def test_equity_70_vs_max_65_fails_by_5_pp():
    result = _eval(_rule(), _metric("equity_weight_pct", 70.0))
    assert result.status == "FAIL"
    assert result.breach_amount == 5.0
    assert result.reason == "Quota azionaria 70,0%: supera il tuo limite 65% di 5,0 punti percentuali"


def test_precision_controls_reason_digits():
    result = _eval(_rule(precision=0), _metric("equity_weight_pct", 70.44))
    assert result.reason == "Quota azionaria 70%: supera il tuo limite 65% di 5 punti percentuali"
    result = _eval(_rule(precision=3), _metric("equity_weight_pct", 70.4444))
    assert "70,444%" in result.reason and "5,444 punti" in result.reason


# -- near limit --------------------------------------------------------------


def test_near_limit_is_an_extra_flag_on_pass():
    result = _eval(_rule(warning_margin=2.0), _metric("equity_weight_pct", 63.5))
    assert result.status == "PASS" and result.near_limit is True
    assert "a 1,5 punti percentuali dalla soglia" in result.reason
    far = _eval(_rule(warning_margin=2.0), _metric("equity_weight_pct", 60.0))
    assert far.status == "PASS" and far.near_limit is False
    at_limit = _eval(_rule(warning_margin=2.0), _metric("equity_weight_pct", 65.0))
    assert at_limit.status == "PASS" and at_limit.near_limit is True
    failed = _eval(_rule(warning_margin=2.0), _metric("equity_weight_pct", 66.0))
    assert failed.near_limit is False


def test_near_limit_on_min_side():
    rule = _rule(metric_code="bond_weight_pct", operator="min", max_value=None, min_value=30.0, warning_margin=1.0)
    assert _eval(rule, _metric("bond_weight_pct", 30.5)).near_limit is True


# -- unknown / null / bounds -------------------------------------------------


def test_missing_metric_is_unknown_never_pass():
    result = _eval(_rule(), _metric("equity_weight_pct", None, lower=None, upper=None, coverage=None, quality="missing"))
    assert result.status == "UNKNOWN"
    assert result.actual is None
    assert result.reason.startswith("Non possiamo verificare il limite")
    assert _eval(_rule(), None).status == "UNKNOWN"


def test_bounds_decisive_even_below_coverage():
    rule = _rule(metric_code="usa_exposure_pct", max_value=60.0, min_coverage_pct=80.0)
    # known 20, unclassified 30 -> at most 50 <= 60: PASS although coverage 70.
    passing = _eval(rule, _metric("usa_exposure_pct", 28.6, lower=20.0, upper=50.0, coverage=70.0, quality="partial"))
    assert passing.status == "PASS"
    # known 65 > 60 whatever the unclassified share: FAIL, breach on the known part.
    failing = _eval(rule, _metric("usa_exposure_pct", 92.9, lower=65.0, upper=95.0, coverage=70.0, quality="partial"))
    assert failing.status == "FAIL"
    assert failing.breach_amount == 5.0
    assert "almeno 65,0%" in failing.reason


def test_point_estimate_never_decides_a_partially_classified_metric():
    # PRD D04: coverage 70 >= minimum 60, point estimate 50 <= 60, but the
    # unclassified share could bring USA to 65 -> UNKNOWN, never PASS.
    rule = _rule(metric_code="usa_exposure_pct", max_value=60.0, min_coverage_pct=60.0)
    result = _eval(rule, _metric("usa_exposure_pct", 50.0, lower=35.0, upper=65.0, coverage=70.0, quality="partial"))
    assert result.status == "UNKNOWN"
    assert "tra 35,0% e 65,0%" in result.reason


def test_usa_known_50_unclassified_15_coverage_85_max_60_is_unknown():
    rule = _rule(metric_code="usa_exposure_pct", max_value=60.0)  # min_coverage default 80
    result = _eval(rule, _metric("usa_exposure_pct", 50 / 85 * 100, lower=50.0, upper=65.0, coverage=85.0, quality="partial"))
    assert result.status == "UNKNOWN"
    assert result.reason.startswith("Non possiamo verificare il limite USA")
    assert "tra 50,0% e 65,0%" in result.reason
    assert "copertura insufficiente" not in result.reason


@pytest.mark.parametrize("operator, values", [("min", {"min_value": 40.0, "max_value": None}),
                                              ("range", {"min_value": 40.0, "max_value": 60.0})])
def test_point_estimate_never_decides_min_and_range(operator, values):
    rule = _rule(metric_code="usa_exposure_pct", operator=operator, **values)
    # estimate 58.8 inside the limits, bounds 50-65 undecided for the range, 35-... for min.
    metric = _metric("usa_exposure_pct", 45.0, lower=35.0, upper=65.0, coverage=85.0, quality="partial")
    assert _eval(rule, metric).status == "UNKNOWN"


def _ter(value, lower, coverage):
    return MetricValue(
        code="weighted_ter_pct", value=value, lower=lower, upper=None, coverage_pct=coverage, quality="partial",
        source="t", denominator="t", denominator_value=1.0,
    )


def test_ter_covered_value_decides_only_above_min_coverage():
    rule = _rule(metric_code="weighted_ter_pct", max_value=0.3, warning_margin=0)
    passing = _eval(rule, _ter(0.2, 0.184, 92.0))
    assert passing.status == "PASS"
    assert passing.quality == "partial"
    assert "su 92% del portafoglio coperto" in passing.reason
    failing = _eval(rule, _ter(0.35, 0.28, 80.0))
    assert failing.status == "FAIL"
    assert failing.quality == "partial"
    assert "su 80% del portafoglio coperto" in failing.reason
    below = _eval(rule, _ter(0.2, 0.12, 60.0))
    assert below.status == "UNKNOWN"
    assert "copertura insufficiente" in below.reason


def test_coverage_below_minimum_and_bounds_undecided_is_unknown():
    rule = _rule(metric_code="usa_exposure_pct", max_value=60.0)
    result = _eval(rule, _metric("usa_exposure_pct", 50.0, lower=35.0, upper=65.0, coverage=70.0, quality="partial"))
    assert result.status == "UNKNOWN"
    assert result.reason.startswith("Non possiamo verificare il limite USA: copertura insufficiente")
    assert result.actual_lower == 35.0 and result.actual_upper == 65.0


def test_ter_lower_bound_can_decide_a_fail():
    rule = _rule(metric_code="weighted_ter_pct", max_value=0.2)
    metric = MetricValue(
        code="weighted_ter_pct", value=0.5, lower=0.3, upper=None, coverage_pct=60.0, quality="partial",
        source="t", denominator="t", denominator_value=1.0,
    )
    result = _eval(rule, metric)
    assert result.status == "FAIL"
    assert result.breach_amount == pytest.approx(0.1)


# -- stale data ---------------------------------------------------------------


def test_stale_prices_are_unknown_not_pass():
    snap = _snapshot(stale_asset_ids=[1])
    result = _eval(_rule(), _metric("equity_weight_pct", 10.0), snap)
    assert result.status == "UNKNOWN"
    assert "quotazioni non aggiornate" in result.reason


def test_price_older_than_max_age_is_unknown():
    holdings = [_h(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 100, "EUR")]
    snap = _snapshot(holdings, price_as_of={1: "2026-10-25"})
    assert _eval(_rule(max_data_age_days=5), _metric("equity_weight_pct", 10.0), snap).status == "UNKNOWN"
    assert _eval(_rule(max_data_age_days=15), _metric("equity_weight_pct", 10.0), snap).status == "PASS"


def test_failed_sync_is_unknown():
    snap = _snapshot(last_sync_status="failed", sync_available=True)
    result = _eval(_rule(), _metric("equity_weight_pct", 10.0), snap)
    assert result.status == "UNKNOWN"
    assert "sincronizzazione" in result.reason


def test_missing_prices_beyond_coverage_tolerance_are_unknown():
    snap = _snapshot(missing_price_asset_ids=[2])  # AGGH = 40% of the value
    assert _eval(_rule(), _metric("equity_weight_pct", 10.0), snap).status == "UNKNOWN"
    assert _eval(_rule(min_coverage_pct=50.0), _metric("equity_weight_pct", 10.0), snap).status == "PASS"


@pytest.mark.parametrize("price_as_of", [{1: "2026-11-03"}, {1: "2026-11-03", 2: None}, {1: "2026-11-03", 2: "not a date"}])
def test_holding_without_price_timestamp_counts_as_missing_price(price_as_of):
    # AGGH (40% of the value) has no usable price timestamp: its age is
    # unknown, so it is treated as a missing price, never as fresh.
    snap = _snapshot(price_as_of=price_as_of)
    result = _eval(_rule(), _metric("equity_weight_pct", 10.0), snap)
    assert result.status == "UNKNOWN"
    assert "manca la quotazione" in result.reason
    # Tolerated when the missing share is within 100 - min_coverage_pct.
    assert _eval(_rule(min_coverage_pct=60.0), _metric("equity_weight_pct", 10.0), snap).status == "PASS"


# -- inactive, empty, no policy, ordering, summary ----------------------------


def test_inactive_rule():
    result = _eval(_rule(enabled=False), _metric("equity_weight_pct", 99.0))
    assert result.status == "INACTIVE"
    assert result.near_limit is False


def test_empty_portfolio_response():
    snap = snapshot_from_holdings([], portfolio_ids=[7])
    response = build_evaluation_response({"rules": [_rule(), _rule(rule_id="r2", metric_code="bond_weight_pct", enabled=False)]}, snap, now=NOW)
    assert response.status == "empty_portfolio"
    assert [r.status for r in response.results] == ["NOT_APPLICABLE", "INACTIVE"]
    assert response.summary.not_applicable == 1


def test_no_policy_response():
    response = build_evaluation_response(None, _snapshot(), now=NOW)
    assert response.status == "no_policy"
    assert response.results == []
    assert response.summary.total == 0
    assert response.scope.fingerprint == "p:7"
    assert response.scope.scope_type == "single"


def test_zero_rule_document_is_ready():
    response = build_evaluation_response({"schema_version": 1, "rules": []}, _snapshot(), now=NOW)
    assert response.status == "ready" and response.summary.total == 0


def test_ordering_and_summary():
    metrics = {
        "equity_weight_pct": _metric("equity_weight_pct", 70.0),        # FAIL low, breach 5
        "bond_weight_pct": _metric("bond_weight_pct", 10.0),            # FAIL high, breach 20
        "gold_weight_pct": _metric("gold_weight_pct", 4.5),             # PASS near
        "top3_positions_pct": _metric("top3_positions_pct", 50.0),      # PASS
        "usa_exposure_pct": _metric("usa_exposure_pct", None, None, None, None, "missing"),  # UNKNOWN
        "max_single_position_pct": _metric("max_single_position_pct", 90.0),  # INACTIVE
        "etf_overlap_pct": _metric("etf_overlap_pct", 80.0),            # FAIL high breach 10
    }
    doc = {"rules": [
        _rule(rule_id="eq", severity="low"),
        _rule(rule_id="bd", metric_code="bond_weight_pct", operator="min", max_value=None, min_value=30, severity="high"),
        _rule(rule_id="gd", metric_code="gold_weight_pct", max_value=5),
        _rule(rule_id="t3", metric_code="top3_positions_pct", max_value=80),
        _rule(rule_id="us", metric_code="usa_exposure_pct", max_value=60),
        _rule(rule_id="ms", metric_code="max_single_position_pct", max_value=35, enabled=False),
        _rule(rule_id="ov", metric_code="etf_overlap_pct", max_value=70, severity="high"),
    ]}
    evaluation = evaluate_policy(doc, metrics, _snapshot(), now=NOW)
    assert [r.rule_id for r in evaluation.results] == ["bd", "ov", "eq", "us", "gd", "t3", "ms"]
    s = evaluation.summary
    assert (s.passed, s.failed, s.unknown, s.inactive, s.near_limit, s.total) == (2, 3, 1, 1, 1, 7)


def test_evidence_and_response_metadata():
    snap = _snapshot()
    response = build_evaluation_response({"rules": [_rule()]}, snap, now=NOW, policy_id=3, policy_version=2, policy_name="Mia")
    result = response.results[0]
    assert result.evidence.methodology_version == "doctor-policy-1.0"
    assert result.evidence.quote_as_of == "2026-11-03"
    assert result.evidence.contributors[0].symbol == "VWCE"
    assert response.snapshot_id == snap.snapshot_id
    assert response.snapshot_as_of == "2026-11-03"
    assert response.calculated_at.startswith("2026-11-04T12:00")
    assert (response.policy_id, response.policy_version, response.policy_name) == (3, 2, "Mia")


def test_reasons_never_sound_like_investment_advice():
    forbidden = ("adeguat", "mifid", "consigli", "raccomand", "pericolos", "dovresti", "devi ")
    metrics = compute_metrics(_snapshot())
    doc = {"rules": [
        _rule(rule_id=f"r{i}", metric_code=code, operator="max", max_value=limit)
        for i, (code, limit) in enumerate([
            ("equity_weight_pct", 10), ("bond_weight_pct", 90), ("gold_weight_pct", 1),
            ("max_single_position_pct", 20), ("top3_positions_pct", 99), ("usa_exposure_pct", 5),
            ("weighted_ter_pct", 0.01), ("etf_overlap_pct", 90),
        ])
    ]}
    for result in evaluate_policy(doc, metrics, _snapshot(), now=NOW).results:
        assert not any(word in result.reason.lower() for word in forbidden), result.reason
