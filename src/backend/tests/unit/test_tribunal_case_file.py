"""Fascicolo dei fatti del Tribunale (TASK-61, docs/tribunale/api-contracts.md §4).

Servizio del Doctor reale (scope, snapshot, metriche, evaluation della policy)
con repository e store finti; i blocchi del Portfolio Doctor (health, X-Ray,
stress, Monte Carlo) sono sostituiti da risposte costruite nel test.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest

from app.repository._scope import NOT_FOUND_MESSAGE
from app.schemas.portfolio_doctor import (
    MonteCarloProjectionResponse,
    MonteCarloYearProjection,
    PortfolioHealthAlert,
    PortfolioHealthCategoryScores,
    PortfolioHealthMetrics,
    PortfolioHealthResponse,
    PortfolioHealthSummary,
    StressTestResponse,
    StressTestScenarioResult,
    XRayResponse,
)
from app.services.doctor_policy import evaluator as evaluator_module
from app.services.doctor_policy import service as service_module
from app.services.doctor_policy.errors import InvalidRequest, NotFound
from app.services.doctor_policy.metrics import compute_metrics
from app.services.doctor_policy.service import DoctorPolicyService
from app.services.doctor_policy.snapshot import snapshot_from_holdings
from app.services.doctor_policy.store import PolicySetRecord
from app.services.portfolio_doctor._holdings import AnalyzedHolding
from app.services.tribunal import case_file as cf_module
from app.services.tribunal.case_file import (
    CASE_FILE_SCHEMA_VERSION,
    CONTRACT_VERSION,
    HASH_FACT_FIELDS,
    MAX_FACTS,
    MAX_INSTRUMENTS,
    MIN_CITABLE_FACTS,
    build_case_file,
    compute_case_file_hash,
    facts_by_id,
    format_fact_value,
)

DOCS = Path(__file__).resolve().parents[4] / "docs" / "tribunale"
FIXTURE = DOCS / "fixtures" / "seduta-esempio.json"
USER = "u1"
OWNED = {1: "EUR", 2: "EUR", 3: "USD", 19: "EUR"}
NOW = datetime(2026, 11, 10, 14, 3, 11, tzinfo=timezone.utc)
POLICY_DOC = {
    "schema_version": 1,
    "rules": [
        {"rule_id": "max-single", "metric_code": "max_single_position_pct", "operator": "max",
         "max_value": 35, "label": "Max singolo ETF"},
        {"rule_id": "bond-min", "metric_code": "bond_weight_pct", "operator": "min", "min_value": 5},
        {"rule_id": "ter-max", "metric_code": "weighted_ter_pct", "operator": "max", "max_value": 0.5},
    ],
}


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------


@dataclass
class _Scope:
    portfolio_ids: list[int]
    base_currency: str


class _Repo:
    engine = object()

    def __init__(self) -> None:
        self.memo_calls = 0

    def resolve_portfolio_scope(self, ids, user_id):
        ids = sorted(set(int(i) for i in ids))
        if user_id != USER or any(i not in OWNED for i in ids):
            raise ValueError(NOT_FOUND_MESSAGE)
        if len({OWNED[i] for i in ids}) > 1:
            raise ValueError("I portafogli aggregati devono avere la stessa valuta base")
        return _Scope(ids, OWNED[ids[0]])

    def memoize_positions(self):
        repo = self

        class _Ctx:
            def __enter__(self):
                repo.memo_calls += 1

            def __exit__(self, *exc):
                return False

        return _Ctx()


class _Store:
    def __init__(self, records=None) -> None:
        self.records = dict(records or {})

    def get_policy_set(self, owner, fingerprint, *, conn=None):
        rec = self.records.get(fingerprint)
        return rec if rec and rec.owner_user_id == owner else None


def _record(fingerprint: str, ids: tuple[int, ...], document=POLICY_DOC) -> PolicySetRecord:
    return PolicySetRecord(
        id=7, owner_user_id=USER, scope_type="single" if len(ids) == 1 else "aggregate",
        scope_fingerprint=fingerprint, name="La mia policy", active=True, current_version=1,
        created_at=NOW, updated_at=NOW, archived_at=None, portfolio_ids=ids, document=document,
    )


def _h(asset_id, symbol, name, asset_type, value, isin, **kw) -> AnalyzedHolding:
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type, quote_currency="EUR",
        market_value=value, weight_pct=0.0, isin=isin, **kw,
    )


def _holdings() -> list[AnalyzedHolding]:
    return [
        _h(1, "VWCE.DE", "Vanguard FTSE All-World UCITS ETF (USD) Accumulating", "etf", 4660, "IE00BK5BQT80",
           index_tracked="FTSE All-World"),
        _h(2, "AGGH", "iShares Core Global Aggregate Bond UCITS ETF EUR Hedged (Dist) ‮evil\x07", "etf",
           1740, "IE00BDBRDM35", investment_focus="Bonds"),
        _h(3, "SXRV.DE", "iShares Nasdaq 100 UCITS ETF (Acc)", "etf", 1420, "IE00B53SZB19",
           index_tracked="NASDAQ 100"),
        _h(4, "EIMI", "iShares Core MSCI EM IMI UCITS ETF (Acc)", "etf", 800, "IE00BKM4GZ66",
           index_tracked="MSCI Emerging Markets IMI"),
        _h(5, "SGLD", "Invesco Physical Gold ETC", "etc", 700, "IE00B579F325", investment_focus="Gold"),
        _h(6, "ENEL.MI", "Enel", "stock", 680, "IT0003128367"),
        _h(7, "CASH", "Liquidità", "cash", 500, None),
    ]


def _health(score=71, volatility=13.8, alerts=None) -> PortfolioHealthResponse:
    if alerts is None:
        alerts = [
            PortfolioHealthAlert(severity="warning", type="position_concentration",
                                 message="Una posizione ha un peso elevato nel portafoglio (46.6%)."),
            PortfolioHealthAlert(severity="warning", type="etf_overlap",
                                 message="Diverse posizioni risultano ridondanti: la sovrapposizione tra ETF è alta (31.5%)."),
        ]
    return PortfolioHealthResponse(
        portfolio_id=19, score=score,
        summary=PortfolioHealthSummary(risk_level="unknown", diversification="unknown", overlap="unknown",
                                       cost_efficiency="unknown"),
        metrics=PortfolioHealthMetrics(portfolio_volatility=volatility, overlap_score=31.5, max_position_weight=46.6),
        category_scores=PortfolioHealthCategoryScores(),
        alerts=alerts,
    )


def _xray() -> XRayResponse:
    return XRayResponse(
        portfolio_id=19, etf_count=4, coverage_pct=88.0, lookthrough_coverage_pct=88.0,
        aggregated_country_exposure={"Stati Uniti": 57.4, "Non classificato": 12.0, "Giappone": 5.2,
                                     "Regno Unito": 3.4, "Francia": 3.4, "Cina": 2.9},
        aggregated_sector_exposure={"Tecnologia": 29.7, "Finanza": 13.1, "Sanità": 9.6, "Energia": 4.0},
    )


def _scenario(sid, name, period, impact, recovery, method="historical", note=None):
    return StressTestScenarioResult(
        scenario_id=sid, scenario_name=name, scenario_type="historical", period=period,
        estimated_portfolio_impact_pct=impact, recovery_months=recovery, risk_level="high", method=method,
        methodology_note=note,
    )


def _stress(**overrides) -> StressTestResponse:
    scenarios = [
        _scenario("gfc_2008", "Global Financial Crisis", "2008", -38.2, 49, "proxy"),
        _scenario("dotcom_crash", "Dot-Com Crash", "2000-2002", -34.5, None, "proxy"),
        _scenario("covid_crash", "Covid Crash", "Feb-Mar 2020", -24.1, 6),
        _scenario("bear_market_2022", "Bear Market 2022", "2022", -17.9, 20),
        StressTestScenarioResult(
            scenario_id="global_equity_crash", scenario_name="Global Equity Crash", scenario_type="shock",
            estimated_portfolio_impact_pct=-30.0, risk_level="critical",
        ),
    ]
    scenarios = [overrides.get(s.scenario_id, s) for s in scenarios]
    return StressTestResponse(portfolio_id=19, scenarios=[s for s in scenarios if s is not None],
                              analysis_date="2026-11-10")


def _mc(empty=False) -> MonteCarloProjectionResponse:
    rows = {10: (101.3, 158.7, 246.2), 20: (118.9, 251.6, 525.0)}
    projections = [] if empty else [
        MonteCarloYearProjection(year=y, p10=v[0], p25=v[0], p50=v[1], p75=v[2], p90=v[2]) for y, v in rows.items()
    ]
    return MonteCarloProjectionResponse(
        portfolio_id=19, num_simulations=5000, horizons=[5, 10, 20], projections=projections,
        annualized_mean_return_pct=6.0, annualized_volatility_pct=13.8,
    )


class _World:
    """Dati di ingresso di un fascicolo, modificabili dal singolo test."""

    def __init__(self) -> None:
        self.holdings = _holdings()
        fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self.snapshot_kwargs: dict = {"price_as_of": {h.asset_id: fresh for h in self.holdings}}
        self.health = _health()
        self.xray = _xray()
        self.stress = _stress()
        self.mc = _mc()
        self.failing: set[str] = set()
        self.calls: list[tuple[str, object]] = []
        self.metric_overrides: dict = {}


@pytest.fixture()
def world(monkeypatch):
    w = _World()

    def fake_snapshot(_repo, ids, _user):
        return snapshot_from_holdings(w.holdings, portfolio_ids=list(ids), base_currency="EUR",
                                      **w.snapshot_kwargs)

    def fake_metrics(snapshot, _repo=None, **kw):
        metrics = compute_metrics(snapshot, None, now=NOW)
        for code, fn in w.metric_overrides.items():
            fn(metrics[code])
        return metrics

    monkeypatch.setattr(service_module, "build_snapshot", fake_snapshot)
    monkeypatch.setattr(service_module, "compute_metrics", fake_metrics)
    monkeypatch.setattr(evaluator_module, "compute_metrics", fake_metrics)

    def block(name, attr):
        def run(repo, ref, user_id, *args, **kwargs):
            w.calls.append((name, ref))
            if name in w.failing:
                raise RuntimeError("boom")
            return getattr(w, attr)
        return run

    monkeypatch.setattr(cf_module, "analyze_portfolio_health", block("health", "health"))
    monkeypatch.setattr(cf_module, "compute_portfolio_xray", block("xray", "xray"))
    monkeypatch.setattr(cf_module, "run_stress_test", block("stress", "stress"))
    monkeypatch.setattr(cf_module, "run_monte_carlo_projection", block("mc", "mc"))
    return w


def _service(records=None) -> DoctorPolicyService:
    return DoctorPolicyService(_Repo(), store=_Store(records))


def _build(ids=(19,), *, records=None, now=NOW, repo=None):
    svc = _service(records)
    return build_case_file(repo or svc.repo, USER, list(ids), service=svc, now=now)


def _schema() -> dict:
    text = (DOCS / "api-contracts.md").read_text(encoding="utf-8")
    section = text.split("### 4.7 JSON Schema", 1)[1]
    block = re.search(r"```json\n(.*?)\n```", section, re.S).group(1)
    return json.loads(block)


def _by_key(case_file) -> dict[str, dict]:
    return {f["key"]: f for f in case_file["facts"]}


def _assert_valid(case_file) -> None:
    jsonschema.validate(case_file, _schema())
    ids = [f["id"] for f in case_file["facts"]]
    assert ids == [f"F{i}" for i in range(1, len(ids) + 1)]
    keys = [f["key"] for f in case_file["facts"]]
    assert len(keys) == len(set(keys))
    assert case_file["hash"] == compute_case_file_hash(case_file)
    assert case_file["counts"] == {
        "total": len(case_file["facts"]),
        "citable": sum(1 for f in case_file["facts"] if f["citable"]),
    }
    for f in case_file["facts"]:
        assert f["sensitive"] is (f["unit"] == "score")
        if not f["citable"]:
            assert f["reason"]
        if f["value"] is None:
            assert f["formatted"] == "N/D" and f["quality"] == "missing" and not f["citable"]
        else:
            decimals = 2 if f["key"] == "metric.weighted_ter_pct" else 1
            assert f["formatted"] == format_fact_value(f["value"], f["unit"], decimals=decimals)


# ---------------------------------------------------------------------------
# portafoglio completo
# ---------------------------------------------------------------------------


def test_constants_match_contract():
    assert CONTRACT_VERSION == "tribunale-1.0"
    assert CASE_FILE_SCHEMA_VERSION == 1
    assert (MAX_FACTS, MIN_CITABLE_FACTS, MAX_INSTRUMENTS) == (40, 6, 30)
    assert HASH_FACT_FIELDS == ("id", "key", "group", "label", "unit", "formatted", "source",
                                "quality", "citable", "reason", "subject", "sensitive")


def test_full_portfolio_case_file(world):
    cf = _build(records={"p:19": _record("p:19", (19,))})
    _assert_valid(cf)
    assert cf["status"] == "ready"
    assert cf["scope"] == {"portfolio_ids": [19], "scope_type": "single", "fingerprint": "p:19"}
    assert cf["generated_at"] == "2026-11-10T14:03:11Z"
    assert cf["methodology_version"] == "doctor-policy-1.0"
    assert cf["notes"] == []
    # single scope: the Doctor services get an int
    assert {name for name, _ in world.calls} == {"health", "xray", "stress", "mc"}
    assert all(ref == 19 for _, ref in world.calls)

    keys = [f["key"] for f in cf["facts"]]
    assert keys == [
        "metric.equity_weight_pct", "metric.bond_weight_pct", "metric.gold_weight_pct",
        "metric.usa_exposure_pct", "metric.max_single_position_pct", "metric.top3_positions_pct",
        "metric.etf_overlap_pct", "positions.count", "metric.weighted_ter_pct",
        "health.score", "health.volatility_pct",
        "health.alert.etf_overlap", "health.alert.position_concentration",
        "xray.coverage_pct", "xray.country.Stati Uniti", "xray.country.Giappone", "xray.country.Francia",
        "xray.sector.Tecnologia", "xray.sector.Finanza", "xray.sector.Sanità",
        "stress.gfc_2008.impact", "stress.gfc_2008.recovery_months",
        "stress.dotcom_crash.impact", "stress.dotcom_crash.recovery_months",
        "stress.covid_crash.impact", "stress.covid_crash.recovery_months",
        "stress.bear_market_2022.impact", "stress.bear_market_2022.recovery_months",
        "mc.y10.p10", "mc.y10.p50", "mc.y10.p90", "mc.y20.p10", "mc.y20.p50", "mc.y20.p90",
        "policy.failed_count", "policy.rule.max-single",
    ]
    f = _by_key(cf)
    # cash excluded from the invested value: VWCE = 4660 / 10000
    assert f["metric.max_single_position_pct"]["value"] == 46.6
    assert f["metric.max_single_position_pct"]["formatted"] == "46,6%"
    assert f["metric.max_single_position_pct"]["subject"] == "VWCE.DE"
    assert f["positions.count"]["value"] == 6 and f["positions.count"]["formatted"] == "6"
    assert f["metric.weighted_ter_pct"]["formatted"].count(",") == 1
    assert re.fullmatch(r"\d+,\d{2}%", f["metric.weighted_ter_pct"]["formatted"])
    assert (f["health.score"]["value"], f["health.score"]["formatted"]) == (71, "71/100")
    assert f["health.score"]["sensitive"] is True
    assert f["health.alert.position_concentration"]["value"] == "attenzione"
    assert f["health.alert.position_concentration"]["label"] == (
        "Avviso del Doctor: Una posizione ha un peso elevato nel portafoglio (46.6%)."
    )
    assert f["xray.coverage_pct"]["reason"] == "Non classificato: 12,0%."
    assert f["xray.country.Stati Uniti"]["subject"] == "Stati Uniti"
    assert f["stress.gfc_2008.impact"]["label"] == "Stress test «Global Financial Crisis» (2008): impatto stimato"
    assert f["stress.gfc_2008.impact"]["formatted"] == "-38,2%"
    assert f["stress.gfc_2008.impact"]["quality"] == "partial" and f["stress.gfc_2008.impact"]["citable"]
    assert f["stress.gfc_2008.recovery_months"]["formatted"] == "49 mesi"
    assert f["stress.covid_crash.impact"]["quality"] == "ok" and f["stress.covid_crash.impact"]["reason"] is None
    assert f["mc.y10.p50"]["label"] == "Monte Carlo a 10 anni, mediana (base 100)"
    assert f["mc.y10.p50"]["formatted"] == "158,7"
    assert f["mc.y20.p90"]["value"] == 525.0 and f["mc.y20.p90"]["formatted"] == "525,0"
    assert f["policy.failed_count"]["value"] == 1
    assert f["policy.rule.max-single"]["label"] == (
        "Tua regola «Max singolo ETF»: Peso massimo singola posizione, al massimo 35%"
    )
    assert f["policy.rule.max-single"]["value"] == "violata" and f["policy.rule.max-single"]["citable"]

    # instruments: by weight, cash excluded, names cleaned and truncated as in the Copilot tools
    assert [i["symbol"] for i in cf["instruments"]] == ["VWCE.DE", "AGGH", "SXRV.DE", "EIMI", "SGLD", "ENEL.MI"]
    aggh = cf["instruments"][1]
    assert "‮" not in aggh["name"] and "\x07" not in aggh["name"]
    assert len(aggh["name"]) == 61 and aggh["name"].endswith("…")
    assert cf["instruments"][0]["isin"] == "IE00BK5BQT80"
    assert facts_by_id(cf)["F1"]["key"] == "metric.equity_weight_pct"


def test_no_llm_dependency():
    source = Path(cf_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("copilot.providers", "copilot.structured", "openai", "anthropic", "llm_call"):
        assert forbidden not in source


def test_uses_positions_memo(world):
    svc = _service()
    build_case_file(svc.repo, USER, [19], service=svc, now=NOW)
    assert svc.repo.memo_calls == 1


# ---------------------------------------------------------------------------
# dati mancanti, stale, UNKNOWN
# ---------------------------------------------------------------------------


def test_missing_data_is_never_zero(world):
    def drop_ter(metric):
        metric.value, metric.quality, metric.coverage_pct = None, "missing", None
        metric.notes = ["TER non disponibile per nessuna posizione."]

    def low_coverage(metric):
        metric.quality, metric.coverage_pct, metric.value = "partial", 55.0, 50.0

    def good_partial(metric):
        metric.quality, metric.coverage_pct = "partial", 91.2
        metric.value, metric.lower, metric.upper = 52.3, 47.7, 56.5

    world.metric_overrides = {"weighted_ter_pct": drop_ter, "usa_exposure_pct": good_partial,
                              "bond_weight_pct": low_coverage}
    world.health = _health(volatility=None, alerts=[])
    world.stress = _stress(covid_crash=_scenario("covid_crash", "Covid Crash", "Feb-Mar 2020", 0.0, None,
                                                 "not_available"),
                           bear_market_2022=None)
    world.mc = _mc(empty=True)
    world.failing = {"xray"}
    records = {"p:19": _record("p:19", (19,), {
        "schema_version": 1,
        "rules": [{"rule_id": "ter-max", "metric_code": "weighted_ter_pct", "operator": "max", "max_value": 0.3}],
    })}
    cf = _build(records=records)
    _assert_valid(cf)
    f = _by_key(cf)

    ter = f["metric.weighted_ter_pct"]
    assert ter["value"] is None and ter["formatted"] == "N/D" and ter["quality"] == "missing"
    assert ter["citable"] is False and ter["reason"] == "TER non disponibile per nessuna posizione."

    usa = f["metric.usa_exposure_pct"]
    assert usa["quality"] == "partial" and usa["citable"] is True
    assert usa["reason"] == "Stima sul 91,2% del valore investito classificato; intervallo tra 47,7% e 56,5%."

    bond = f["metric.bond_weight_pct"]
    assert bond["quality"] == "partial" and bond["citable"] is False
    assert bond["reason"] == "Copertura insufficiente (55,0%)."

    vol = f["health.volatility_pct"]
    assert vol["value"] is None and not vol["citable"] and vol["reason"]
    assert not any(k.startswith("health.alert.") for k in f)

    # failed X-Ray block: fixed row missing, variable rows absent
    assert f["xray.coverage_pct"]["value"] is None
    assert f["xray.coverage_pct"]["reason"] == "Dato non disponibile: X-Ray non calcolabile."
    assert not any(k.startswith(("xray.country.", "xray.sector.")) for k in f)

    # not_available scenario: no 0,0% impact; scenario not computed: both rows missing
    for sid in ("covid_crash", "bear_market_2022"):
        assert f[f"stress.{sid}.impact"]["value"] is None
        assert f[f"stress.{sid}.recovery_months"]["value"] is None
    rec = f["stress.dotcom_crash.recovery_months"]
    assert rec["formatted"] == "N/D" and rec["reason"] == "Tempo di recupero non disponibile per questo scenario."
    assert f["stress.dotcom_crash.impact"]["citable"] is True

    for key in ("mc.y10.p10", "mc.y10.p50", "mc.y10.p90", "mc.y20.p10", "mc.y20.p50", "mc.y20.p90"):
        assert f[key]["value"] is None and not f[key]["citable"]

    rule = f["policy.rule.ter-max"]
    assert rule["value"] == "non verificabile" and rule["formatted"] == "non verificabile"
    assert rule["quality"] == "partial" and rule["citable"] is False and rule["reason"]
    assert f["policy.failed_count"]["value"] == 0

    # no fact with a missing value is shown as zero
    assert all(fact["value"] not in (0, 0.0) or fact["quality"] != "missing" for fact in cf["facts"])


def test_stale_quotes_make_metrics_not_citable(world):
    world.snapshot_kwargs["stale_asset_ids"] = [1]
    cf = _build()
    _assert_valid(cf)
    metric_facts = [f for f in cf["facts"] if f["key"].startswith("metric.")]
    assert len(metric_facts) == 8
    for fact in metric_facts:
        assert fact["quality"] in ("stale", "missing") and fact["citable"] is False
        if fact["quality"] == "stale":
            assert fact["value"] is not None
            assert fact["reason"] == "Quotazioni non aggiornate: VWCE.DE."
    assert "Quotazioni non aggiornate: VWCE.DE." in cf["notes"]
    # other sources do not track freshness
    assert _by_key(cf)["health.score"]["quality"] == "ok"


def test_failed_blocks_do_not_fail_case_file(world):
    world.failing = {"health", "xray", "stress", "mc"}
    cf = _build()
    _assert_valid(cf)
    f = _by_key(cf)
    assert len([k for k in f if k.startswith("metric.")]) == 8
    assert f["health.score"]["reason"] == "Dato non disponibile: health score non calcolabile."
    assert f["health.score"]["sensitive"] is True and f["health.score"]["formatted"] == "N/D"
    assert len([k for k in f if k.startswith("stress.")]) == 8
    assert all(f[k]["value"] is None for k in f if k.startswith(("stress.", "mc.")))
    assert "policy.failed_count" not in f  # no policy for the scope


# ---------------------------------------------------------------------------
# vista aggregata e proprietà
# ---------------------------------------------------------------------------


def test_aggregate_view(world):
    cf = _build(ids=[2, 1, 2], records={"p:1,2": _record("p:1,2", (1, 2))})
    _assert_valid(cf)
    assert cf["scope"] == {"portfolio_ids": [1, 2], "scope_type": "aggregate", "fingerprint": "p:1,2"}
    assert cf["notes"][0] == "Vista aggregata di 2 portafogli."
    assert all(ref == [1, 2] for _, ref in world.calls)
    assert "policy.failed_count" in _by_key(cf)


def test_scope_not_owned_raises_doctor_not_found(world):
    with pytest.raises(NotFound) as excinfo:
        _build(ids=[1, 99])
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "not_found"
    assert excinfo.value.message == NOT_FOUND_MESSAGE
    # same error as the Doctor service
    with pytest.raises(NotFound) as doctor:
        _service().resolve_scope([1, 99], USER)
    assert doctor.value.message == excinfo.value.message
    assert world.calls == []


def test_invalid_scope_raises_invalid_request(world):
    with pytest.raises(InvalidRequest):
        _build(ids=[1, 3])  # mixed currencies
    with pytest.raises(InvalidRequest):
        _build(ids=[0])


# ---------------------------------------------------------------------------
# stabilità dell'hash
# ---------------------------------------------------------------------------


def test_hash_is_stable_and_changes_with_values(world):
    first = _build(records={"p:19": _record("p:19", (19,))})
    second = _build(records={"p:19": _record("p:19", (19,))}, now=datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert first["generated_at"] != second["generated_at"]
    assert [f["id"] for f in first["facts"]] == [f["id"] for f in second["facts"]]
    assert first["facts"] == second["facts"]
    assert first["hash"] == second["hash"]

    world.mc = MonteCarloProjectionResponse(**{
        **_mc().model_dump(),
        "projections": [{**p.model_dump(), "p50": p.p50 + 0.1} for p in _mc().projections],
    })
    third = _build(records={"p:19": _record("p:19", (19,))})
    assert third["hash"] != first["hash"]
    assert [f["key"] for f in third["facts"]] == [f["key"] for f in first["facts"]]


def test_hash_excludes_service_fields_and_tracks_quality():
    cf = json.loads(FIXTURE.read_text(encoding="utf-8"))["session"]["case_file"]
    assert compute_case_file_hash(cf) == cf["hash"]
    changed = copy.deepcopy(cf)
    changed.update(generated_at="2030-01-01T00:00:00Z", as_of=None, notes=["x"], counts={"total": 0, "citable": 0},
                   status="empty_portfolio", hash="0" * 64)
    assert compute_case_file_hash(changed) == cf["hash"]
    changed["facts"][0]["citable"] = False
    assert compute_case_file_hash(changed) != cf["hash"]


def test_hash_follows_formatted_not_value():
    cf = json.loads(FIXTURE.read_text(encoding="utf-8"))["session"]["case_file"]
    fact = facts_by_id(cf)["F1"]
    assert fact["formatted"] == "75,6%"
    same = copy.deepcopy(cf)
    facts_by_id(same)["F1"]["value"] = 75.6123  # still "75,6%"
    assert compute_case_file_hash(same) == cf["hash"]
    other = copy.deepcopy(cf)
    facts_by_id(other)["F1"].update(value=75.7, formatted="75,7%")
    assert compute_case_file_hash(other) != cf["hash"]


def test_price_update_without_visible_change_keeps_hash(world):
    first = _build()
    world.mc = MonteCarloProjectionResponse(**{
        **_mc().model_dump(),
        "projections": [{**p.model_dump(), "p50": p.p50 + 0.01} for p in _mc().projections],
    })
    second = _build()
    assert _by_key(first)["mc.y10.p50"]["value"] != _by_key(second)["mc.y10.p50"]["value"]
    assert _by_key(first)["mc.y10.p50"]["formatted"] == _by_key(second)["mc.y10.p50"]["formatted"]
    assert first["hash"] == second["hash"]


def test_fixture_case_file_matches_schema_and_formatting():
    cf = json.loads(FIXTURE.read_text(encoding="utf-8"))["session"]["case_file"]
    _assert_valid(cf)


# ---------------------------------------------------------------------------
# portafoglio vuoto
# ---------------------------------------------------------------------------


def test_empty_portfolio(world):
    world.holdings = [_h(7, "CASH", "Liquidità", "cash", 500, None)]
    cf = _build()
    _assert_valid(cf)
    assert cf["status"] == "empty_portfolio"
    assert cf["facts"] == [] and cf["instruments"] == []
    assert cf["counts"] == {"total": 0, "citable": 0}
    assert world.calls == []


# ---------------------------------------------------------------------------
# formattazione, limiti, priorità
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("value", "unit", "decimals", "expected"), [
    (46.6, "pct", 1, "46,6%"),
    (0.19, "pct", 2, "0,19%"),
    (-38.2, "pct", 1, "-38,2%"),
    (-0.0, "pct", 1, "0,0%"),
    (71, "score", 1, "71/100"),
    (6, "count", 1, "6"),
    (1204, "count", 1, "1.204"),
    (158.7, "index", 1, "158,7"),
    (1, "months", 1, "1 mese"),
    (49, "months", 1, "49 mesi"),
    ("violata", "text", 1, "violata"),
    (None, "pct", 1, "N/D"),
])
def test_format_fact_value(value, unit, decimals, expected):
    assert format_fact_value(value, unit, decimals=decimals) == expected


def test_alerts_deduplicated_sorted_and_limited(world):
    world.health = _health(alerts=[
        PortfolioHealthAlert(severity="info", type="z_info", message="Info."),
        PortfolioHealthAlert(severity="warning", type="position_concentration", message="Peso elevato."),
        PortfolioHealthAlert(severity="critical", type="position_concentration", message="Domina."),
        PortfolioHealthAlert(severity="warning", type="high_costs", message="Costi alti."),
        PortfolioHealthAlert(severity="warning", type="portfolio_risk", message="Rischio."),
    ])
    cf = _build()
    alerts = [f for f in cf["facts"] if f["key"].startswith("health.alert.")]
    assert [a["key"] for a in alerts] == [
        "health.alert.position_concentration", "health.alert.high_costs", "health.alert.portfolio_risk",
    ]
    assert alerts[0]["value"] == "critico" and alerts[0]["label"] == "Avviso del Doctor: Domina."


def test_trim_respects_max_facts_and_priorities():
    def fact(key, group):
        return cf_module._fact(key, group, key, 1.0, "pct", "xray")

    facts = [fact(f"metric.m{i}", "composizione") for i in range(8)] + [fact("health.score", "salute")]
    facts += [fact(f"health.alert.a{i}", "salute") for i in range(10)]
    facts += [fact(f"xray.country.c{i}", "esposizione") for i in range(10)]
    facts += [fact(f"stress.s{i}.impact", "stress") for i in range(10)]
    facts += [fact(f"policy.rule.r{i}", "regole") for i in range(10)]
    trimmed = cf_module._trim(facts)
    assert len(trimmed) == MAX_FACTS
    keys = [f["key"] for f in trimmed]
    assert keys == [k for k in (f["key"] for f in facts) if k in keys]  # order preserved
    assert all(f"metric.m{i}" in keys for i in range(8)) and "health.score" in keys
    # 49 facts: the last group's variable rows go first, from the bottom
    assert [k for k in keys if k.startswith("policy.rule.")] == ["policy.rule.r0"]
    assert all(f"stress.s{i}.impact" in keys for i in range(10))
    assert len([k for k in keys if k.startswith(("health.alert.", "xray.country."))]) == 20

    # more facts: then the earlier groups lose their variable rows from the bottom
    more = facts + [fact(f"mc.y{i}", "scenari") for i in range(10)]
    keys = [f["key"] for f in cf_module._trim(more)]
    assert len(keys) == MAX_FACTS
    assert not any(k.startswith("policy.rule.") for k in keys)
    assert [k for k in keys if k.startswith("xray.country.")] == ["xray.country.c0"]
    assert len([k for k in keys if k.startswith("health.alert.")]) == 10
    assert all(f"metric.m{i}" in keys for i in range(8)) and "health.score" in keys


def test_labels_and_subjects_are_cleaned(world):
    world.xray = XRayResponse(
        portfolio_id=19, etf_count=1, coverage_pct=50.0, lookthrough_coverage_pct=50.0,
        aggregated_country_exposure={"Stati​ Uniti‮": 40.0},
        aggregated_sector_exposure={},
    )
    cf = _build()
    _assert_valid(cf)
    country = next(f for f in cf["facts"] if f["key"].startswith("xray.country."))
    assert country["subject"] == "Stati Uniti"
    assert country["key"] == "xray.country.Stati Uniti"
    assert _by_key(cf)["xray.coverage_pct"]["reason"] is None
