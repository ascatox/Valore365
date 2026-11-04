"""TASK-PERF-01: MWR exposed by the MCP performance tools (single and aggregate)."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import app.copilot_tools as copilot_tools
import app.services.performance_service as performance_module
from app.mcp_server.aggregate_tools import AGGREGATE_TOOLS
from app.models import CashFlowEntry, MWRResult, PerformanceSummary, TWRResult
from app.repository import PortfolioScope
from app.services.performance_service import PerformanceService

PERIODS = ("1m", "3m", "ytd", "1y")
LEGACY_KEYS = {"twr_1m", "twr_3m", "twr_ytd", "twr_1y", "implicit_contributions_eur", "implicit_contributions_note"}
NEW_KEYS = {
    "mwr_1m", "mwr_3m", "mwr_ytd", "mwr_1y", "mwr_converged", "mwr_annualized_pct", "mwr_null_reason",
    "mwr_multiple_roots", "calculation_windows", "twr_annualized_pct", "performance_note",
}


def _summary(period: str, twr: float | None, mwr: float | None, *, converged: bool = True,
             days: int = 30, twr_ann: float | None = None, mwr_ann: float | None = None,
             implicit: float = 0.0, mwr_start: str | None = None) -> PerformanceSummary:
    end = date(2026, 11, 4)
    start = (end - timedelta(days=days)).isoformat()
    return PerformanceSummary(
        period=period, period_label=period, start_date=start, end_date=end.isoformat(), period_days=days,
        twr=TWRResult(twr_pct=twr, twr_annualized_pct=twr_ann, period_days=days, start_date=start,
                      end_date=end.isoformat()),
        mwr=MWRResult(mwr_pct=mwr, mwr_annualized_pct=mwr_ann, period_days=days, start_date=mwr_start or start,
                      end_date=end.isoformat(), converged=converged),
        total_deposits=0.0, total_withdrawals=0.0, net_invested=0.0, initial_value=1000.0,
        current_value=1100.0, absolute_gain=100.0, implicit_contributions=implicit,
    )


class _FakePerf:
    def __init__(self, summaries: dict[str, object]) -> None:
        self.summaries = summaries
        self.calls: list[tuple] = []

    def get_performance_summary(self, portfolio_id, user_id, period):
        self.calls.append((portfolio_id, user_id, period))
        item = self.summaries[period]
        if isinstance(item, Exception):
            raise item
        return item


def test_legacy_keys_unchanged_and_mwr_fields_added_with_one_call_per_period():
    perf = _FakePerf({
        "1m": _summary("1m", 1.234, 1.456, days=31),
        "3m": _summary("3m", 2.345, 2.111, days=92),
        "ytd": _summary("ytd", 5.678, 6.789, days=307, implicit=12.345),
        "1y": _summary("1y", 10.004, 11.116, days=365, twr_ann=10.004, mwr_ann=11.116, mwr_start="2025-11-05"),
    })

    out = copilot_tools._get_performance({}, None, perf, 7, "u")

    assert perf.calls == [(7, "u", p) for p in PERIODS]
    assert set(out) == LEGACY_KEYS | NEW_KEYS
    # Legacy keys: same values and shape as before.
    assert (out["twr_1m"], out["twr_3m"], out["twr_ytd"], out["twr_1y"]) == (1.23, 2.35, 5.68, 10.0)
    assert out["implicit_contributions_eur"] == {"1m": 0.0, "3m": 0.0, "ytd": 12.35, "1y": 0.0}
    assert out["implicit_contributions_note"].startswith("Apporti impliciti per periodo")
    # New keys.
    assert (out["mwr_1m"], out["mwr_3m"], out["mwr_ytd"], out["mwr_1y"]) == (1.46, 2.11, 6.79, 11.12)
    assert out["mwr_converged"] == dict.fromkeys(PERIODS, True)
    assert out["mwr_null_reason"] == dict.fromkeys(PERIODS)
    assert out["mwr_multiple_roots"] == dict.fromkeys(PERIODS, False)  # MWRResult default
    assert out["mwr_annualized_pct"] == {"1m": None, "3m": None, "ytd": None, "1y": 11.12}
    assert out["twr_annualized_pct"] == {"1m": None, "3m": None, "ytd": None, "1y": 10.0}
    assert out["calculation_windows"]["1m"] == {
        "start_date": "2026-10-04", "end_date": "2026-11-04", "period_days": 31,
        "twr_start_date": "2026-10-04", "twr_end_date": "2026-11-04",
        "mwr_start_date": "2026-10-04", "mwr_end_date": "2026-11-04",
    }
    assert out["calculation_windows"]["1y"]["mwr_start_date"] == "2025-11-05"
    note = out["performance_note"]
    for text in ("non annualizzati", "XIRR", "ACT/365", "fine giornata", "versamenti esterni", "combinati"):
        assert text in note


def test_multiple_roots_is_read_when_the_service_provides_it():
    ps = _summary("1m", 1.0, 2.0)
    ps_ns = SimpleNamespace(**{**ps.__dict__, "mwr": SimpleNamespace(**{**ps.mwr.__dict__, "multiple_roots": True})})
    perf = _FakePerf({p: ps_ns for p in PERIODS})

    out = copilot_tools._get_performance({}, None, perf, 1, "u")

    assert out["mwr_multiple_roots"] == dict.fromkeys(PERIODS, True)


def test_null_and_non_converged_mwr_report_a_reason():
    perf = _FakePerf({
        "1m": _summary("1m", 1.0, None, converged=False),
        "3m": _summary("3m", 1.0, None, converged=True),
        "ytd": _summary("ytd", None, 3.0),
        "1y": _summary("1y", 1.0, 2.0),
    })

    out = copilot_tools._get_performance({}, None, perf, 1, "u")

    assert out["mwr_1m"] is None and out["mwr_3m"] is None
    assert out["mwr_converged"]["1m"] is False
    assert out["mwr_null_reason"] == {"1m": "non_convergente", "3m": "non_calcolabile", "ytd": None, "1y": None}
    assert out["twr_1m"] == 1.0 and out["twr_ytd"] is None and out["mwr_ytd"] == 3.0


def test_exception_on_a_period_nulls_every_field_of_that_period():
    perf = _FakePerf({
        "1m": _summary("1m", 1.0, 2.0),
        "3m": RuntimeError("boom"),
        "ytd": _summary("ytd", 1.0, 2.0),
        "1y": _summary("1y", 1.0, 2.0),
    })

    out = copilot_tools._get_performance({}, None, perf, 1, "u")

    assert len(perf.calls) == 4
    assert out["twr_3m"] is None and out["mwr_3m"] is None
    assert out["implicit_contributions_eur"]["3m"] is None
    for key in ("mwr_converged", "mwr_annualized_pct", "twr_annualized_pct", "mwr_multiple_roots",
                "calculation_windows"):
        assert out[key]["3m"] is None
    assert out["mwr_null_reason"]["3m"] == "errore_calcolo"
    assert out["mwr_1m"] == 2.0


def test_legacy_minimal_summary_object_still_works():
    # Old-style stub with only twr (as in the integration tests): no crash, MWR null.
    perf = _FakePerf({p: SimpleNamespace(twr=SimpleNamespace(twr_pct=1.234)) for p in PERIODS})

    out = copilot_tools._get_performance({}, None, perf, 1, "u")

    assert out["twr_1y"] == 1.23
    assert out["mwr_1y"] is None
    assert out["mwr_null_reason"]["1y"] == "errore_calcolo"


# --- Real PerformanceService on a fake repo -----------------------------------

TODAY = date(2026, 11, 4)
INCEPTION = TODAY - timedelta(days=500)


class _FixedDate(date):
    @classmethod
    def today(cls):
        return TODAY


def _cf(day: date, side: str, amount: float) -> CashFlowEntry:
    return CashFlowEntry(date=day.isoformat(), side=side, amount=amount)


class _FakeRepo:
    def __init__(self, values, cashflows):
        self.values = values
        self.cashflows = cashflows

    def resolve_portfolio_scope(self, portfolio_ids, user_id):
        return PortfolioScope(portfolio_ids=tuple(dict.fromkeys(portfolio_ids)), base_currency="EUR")

    def get_portfolio_inception_date(self, portfolio_id, user_id):
        return INCEPTION

    def get_portfolio_inception_date_multi(self, portfolio_ids, user_id):
        return INCEPTION

    def get_external_cashflows(self, portfolio_id, user_id, start_date=None, end_date=None, include_trades=False):
        return self._window(self.cashflows.get(portfolio_id, []), start_date, end_date, include_trades)

    def get_external_cashflows_by_portfolio(self, portfolio_ids, user_id, start_date=None, end_date=None,
                                            include_trades=False):
        return {pid: self._window(self.cashflows.get(pid, []), start_date, end_date, include_trades)
                for pid in portfolio_ids}

    def get_portfolio_values_in_range(self, portfolio_id, user_id, target_dates):
        return {d: self._value(portfolio_id, d) for d in target_dates}

    def get_portfolio_values_in_range_multi(self, portfolio_ids, user_id, target_dates):
        return {d: round(sum(self._value(pid, d) for pid in portfolio_ids), 2) for d in target_dates}

    def _value(self, pid, day):
        series = self.values[pid]
        known = [d for d in series if d <= day]
        return float(series[max(known)]) if known else 0.0

    @staticmethod
    def _window(flows, start, end, include_trades):
        sides = {"deposit", "withdrawal", "dividend", "fee", "interest"} | ({"buy", "sell"} if include_trades else set())
        return [cf for cf in flows if cf.side in sides
                and (start is None or date.fromisoformat(cf.date) >= start)
                and (end is None or date.fromisoformat(cf.date) <= end)]


def test_aggregate_handler_mwr_matches_the_service(monkeypatch):
    monkeypatch.setattr(performance_module, "date", _FixedDate)
    d = lambda n: TODAY - timedelta(days=n)  # noqa: E731
    repo = _FakeRepo(
        values={
            1: {INCEPTION: 1000.0, d(400): 1050.0, d(200): 1600.0, d(80): 1700.0, d(20): 2300.0, d(0): 2400.0},
            2: {INCEPTION: 500.0, d(300): 520.0, d(100): 900.0, d(10): 950.0, d(0): 960.0},
        },
        cashflows={
            1: [_cf(INCEPTION, "deposit", 1000.0), _cf(d(200), "deposit", 500.0), _cf(d(20), "deposit", 500.0)],
            2: [_cf(INCEPTION, "deposit", 500.0), _cf(d(100), "deposit", 350.0)],
        },
    )
    service = PerformanceService(repo)
    deps = SimpleNamespace(repo=repo, performance_service=service, finance_client=None)

    out = AGGREGATE_TOOLS["get_aggregate_performance"].handler(deps, [1, 2], "u")

    for p in PERIODS:
        ps = service.get_performance_summary([1, 2], "u", p)
        assert ps.mwr.mwr_pct is not None
        assert out[f"mwr_{p}"] == round(ps.mwr.mwr_pct, 2)
        assert out[f"twr_{p}"] == round(ps.twr.twr_pct, 2)
        assert out["calculation_windows"][p]["mwr_start_date"] == ps.mwr.start_date
    assert out["mwr_1y"] != out["twr_1y"]  # the flows make the two measures differ
    assert out["mwr_annualized_pct"]["1y"] == pytest.approx(out["mwr_1y"], abs=0.5)
