"""TASK-PERF-02: read-only diagnostic export of TWR/MWR inputs and the offline auditor."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

import pytest

import app.mcp_server.tools as mcp_tools
from app.mcp_server.aggregate_tools import AGGREGATE_TOOLS
from app.mcp_server.freshness import FRESHNESS_TOOLS
from app.models import CashFlowEntry
from app.repository import PortfolioScope
from app.services.performance_audit import MAX_AUDIT_FLOWS, build_performance_audit_export
from app.services.performance_service import PerformanceService

_AUDITOR_PATH = Path(__file__).resolve().parents[4] / "scripts" / "audit" / "twr_mwr_offline_auditor.py"
_spec = importlib.util.spec_from_file_location("twr_mwr_offline_auditor", _AUDITOR_PATH)
auditor = importlib.util.module_from_spec(_spec)
sys.modules["twr_mwr_offline_auditor"] = auditor
_spec.loader.exec_module(auditor)

USER = "u"
START = date(2026, 1, 1)
FEB = date(2026, 2, 1)
MAR = date(2026, 3, 1)
MID = date(2026, 4, 1)
END = date(2026, 7, 1)


def _cf(day: date, side: str, amount: float) -> CashFlowEntry:
    return CashFlowEntry(date=day.isoformat(), side=side, amount=amount)


class _FakeRepo:
    """Per-portfolio step value series and cashflows (read methods only)."""

    def __init__(self, values, cashflows, inception: date = START) -> None:
        self.values = values
        self.cashflows = cashflows
        self.inception = inception
        self.calls: list[str] = []

    def resolve_portfolio_scope(self, portfolio_ids, user_id):
        ids = list(dict.fromkeys(i for i in portfolio_ids if i > 0))
        if user_id != USER or any(i not in self.values for i in ids):
            raise ValueError("Portfolio non trovato")
        return PortfolioScope(portfolio_ids=tuple(ids), base_currency="EUR")

    def get_portfolio_inception_date(self, portfolio_id, user_id):
        return self.inception

    def get_portfolio_inception_date_multi(self, portfolio_ids, user_id):
        return self.inception

    def get_external_cashflows(self, portfolio_id, user_id, start_date=None, end_date=None, include_trades=False):
        self.calls.append("cashflows")
        return self._window(self.cashflows.get(portfolio_id, []), start_date, end_date, include_trades)

    def get_external_cashflows_by_portfolio(self, portfolio_ids, user_id, start_date=None, end_date=None,
                                            include_trades=False):
        self.calls.append("cashflows_multi")
        return {
            pid: self._window(self.cashflows.get(pid, []), start_date, end_date, include_trades)
            for pid in portfolio_ids
        }

    def get_portfolio_values_in_range(self, portfolio_id, user_id, target_dates):
        return {d: self._value(portfolio_id, d) for d in target_dates}

    def get_portfolio_values_in_range_multi(self, portfolio_ids, user_id, target_dates):
        return {d: round(sum(self._value(pid, d) for pid in portfolio_ids), 2) for d in target_dates}

    def get_current_cash_balance_detail_multi(self, portfolio_ids, user_id):
        return type("Detail", (), {"fx_missing_currencies": ["USD"]})()

    def _value(self, pid, day):
        series = self.values[pid]
        known = [d for d in series if d <= day]
        return float(series[max(known)]) if known else 0.0

    @staticmethod
    def _window(flows, start, end, include_trades):
        sides = {"deposit", "withdrawal", "dividend", "fee", "interest"}
        if include_trades:
            sides |= {"buy", "sell"}
        return [
            cf for cf in flows
            if cf.side in sides
            and (start is None or date.fromisoformat(cf.date) >= start)
            and (end is None or date.fromisoformat(cf.date) <= end)
        ]


def _scenario(end_flow: bool = False, shift: timedelta = timedelta(0)) -> _FakeRepo:
    """Two portfolios: deposits, a buy beyond cash (implicit), a same-day cross transfer."""
    s, feb, mar, mid, end = (d + shift for d in (START, FEB, MAR, MID, END))
    p1_cash = [_cf(s, "deposit", 1000.0), _cf(feb, "deposit", 500.0), _cf(mid, "withdrawal", -300.0)]
    p1_values = {s: 1000.0, feb: 1520.0, mid: 1250.0, end: 1300.0}
    if end_flow:
        p1_cash.append(_cf(end, "deposit", 100.0))
        p1_values[end] = 1400.0
    return _FakeRepo(
        values={1: p1_values, 2: {s: 1000.0, mar: 1510.0, mid: 1800.0, end: 1900.0}},
        cashflows={
            1: p1_cash,
            # 1500 buy with 1000 cash: 500 implicit contribution (cash model).
            2: [_cf(s, "deposit", 1000.0), _cf(mar, "buy", 1500.0), _cf(mid, "deposit", 300.0)],
        },
        inception=s,
    )


def _export(repo, ids=(1, 2), **kwargs):
    service = PerformanceService(repo)
    kwargs.setdefault("start_date", START)
    kwargs.setdefault("end_date", END)
    return service, build_performance_audit_export(service, list(ids) if not isinstance(ids, int) else ids,
                                                   USER, **kwargs)


def _key(flow):
    return (flow["date"], flow["side"], round(flow["amount_eur"], 6))


def test_export_flows_are_exactly_the_service_flows_with_attribution():
    service, export = _export(_scenario())
    flows, _ = service._get_cashflows_with_fallback([1, 2], USER, START, END)

    assert sorted(_key(f) for f in export["external_flows"]) == sorted(
        (cf.date, cf.side, round(cf.amount, 6)) for cf in flows
    )
    assert export["consistency_check"]["flows_match_service"] is True
    assert export["consistency_check"]["totals_match"] is True
    assert export["total_flows"] == len(flows) == 6

    by_key = {(f["date"], f["side"], f["portfolio_id"]): f for f in export["external_flows"]}
    implicit = by_key[(MAR.isoformat(), "implicit_contribution", 2)]
    assert implicit["amount_eur"] == pytest.approx(500.0)
    assert implicit["synthetic_flow"] is True and implicit["source"] == "cash_model"
    assert implicit["reason"] == "cash_shortfall_end_of_day"
    assert export["implicit_flows"] == [implicit]
    assert by_key[(MID.isoformat(), "withdrawal", 1)]["amount_eur"] == -300.0
    assert by_key[(MID.isoformat(), "deposit", 2)]["source"] == "transaction"
    assert by_key[(MID.isoformat(), "deposit", 2)]["synthetic_flow"] is False
    # Start-day deposits are inside the start value.
    assert [f["in_twr_mwr"] for f in export["external_flows"] if f["date"] == START.isoformat()] == [False, False]
    assert all(f["in_twr_mwr"] for f in export["external_flows"] if f["date"] != START.isoformat())


def test_export_nets_transfers_and_reports_valuations():
    _, export = _export(_scenario())

    net = {row["date"]: row["amount_eur"] for row in export["net_flows_by_date"]}
    assert net == {START.isoformat(): 2000.0, FEB.isoformat(): 500.0, MAR.isoformat(): 500.0, MID.isoformat(): 0.0}
    vals = {row["date"]: row["value_eur"] for row in export["valuation_on_flow_dates"]}
    assert vals == {START.isoformat(): 2000.0, FEB.isoformat(): 2520.0, MAR.isoformat(): 3030.0,
                    MID.isoformat(): 3050.0, END.isoformat(): 3200.0}
    assert (export["valuation_start"], export["valuation_before_start"], export["valuation_end"]) == (2000.0, 0.0, 3200.0)
    assert export["portfolio_ids"] == [1, 2] and export["period"] == "custom"
    assert export["period_days"] == (END - START).days
    assert export["valuation_method"].startswith("end_of_day")
    assert export["data_quality"]["fx_missing"] == ["USD"]
    assert export["data_quality"]["prices_missing"] == []
    assert export["service_results"]["twr"]["twr_pct"] is not None
    json.dumps(export)  # JSON-serializable


def test_export_pagination_and_validation():
    repo = _scenario()
    _, page = _export(repo, max_flows=2, offset=1)
    _, full = _export(repo)
    assert page["external_flows"] == full["external_flows"][1:3]
    assert (page["total_flows"], page["offset"], page["limit"], page["truncated"]) == (6, 1, 2, True)
    assert full["truncated"] is False
    # Net flows and valuations are never paginated (the auditor needs them all).
    assert page["net_flows_by_date"] == full["net_flows_by_date"]

    _, capped = _export(repo, max_flows=10_000)
    assert capped["limit"] == MAX_AUDIT_FLOWS
    _, beyond = _export(repo, offset=50)
    assert beyond["external_flows"] == [] and beyond["truncated"] is False
    with pytest.raises(ValueError, match="offset"):
        _export(repo, offset=-1)
    with pytest.raises(ValueError, match="max_flows"):
        _export(repo, max_flows=0)
    with pytest.raises(ValueError, match="Portfolio non trovato"):
        build_performance_audit_export(PerformanceService(repo), [1, 2], "other-user", start_date=START, end_date=END)


def test_single_portfolio_export_matches_service():
    service, export = _export(_scenario(), ids=2)
    flows, _ = service._get_cashflows_with_fallback(2, USER, START, END)
    assert export["portfolio_ids"] == [2]
    assert export["consistency_check"]["flows_match_service"] is True
    assert {f["portfolio_id"] for f in export["external_flows"]} == {2}
    assert len(export["external_flows"]) == len(flows) == 3


def test_offline_auditor_reproduces_service_twr_and_mwr():
    _, export = _export(_scenario())
    result = auditor.audit(json.loads(json.dumps(export)))

    service = export["service_results"]
    # Independent hand computation of the chained TWR.
    expected = (1 + 20 / 2000) * (1 + 10 / 2520) * (1 + 20 / 3030) * (1 + 150 / 3050) - 1
    assert result["twr"]["twr_pct"] == pytest.approx(expected * 100, abs=1e-6)
    assert result["rows"][0]["auditor"] == pytest.approx(service["twr"]["twr_pct"], abs=0.01)
    assert result["rows"][1]["auditor"] == pytest.approx(service["mwr"]["mwr_pct"], abs=0.01)
    assert result["ok"] is True
    assert abs(result["xirr"]["npv_residual"]) < 1e-6
    assert result["xirr"]["multiple_roots"] is False


def test_offline_auditor_cli_exit_codes(tmp_path):
    _, export = _export(_scenario())
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export))
    out = io.StringIO()
    with redirect_stdout(out):
        assert auditor.main([str(path)]) == 0
    assert "TWR %" in out.getvalue() and "residuo NPV" in out.getvalue()

    export["service_results"]["twr"]["twr_pct"] += 0.5
    path.write_text(json.dumps(export))
    with redirect_stdout(io.StringIO()):
        assert auditor.main([str(path)]) == 1


def test_offline_auditor_flags_multiple_irr_roots():
    # Classic -100 / +230 / -132: NPV zero at 10% and 20%.
    cashflows = [(0.0, -100.0), (1.0, 230.0), (2.0, -132.0)]
    roots = [auditor.bisect(cashflows, lo, hi) for lo, hi in auditor.find_brackets(cashflows)]
    assert len(roots) == 2
    assert roots[0] == pytest.approx(0.1, abs=1e-6) and roots[1] == pytest.approx(0.2, abs=1e-6)


def _end_flow_export():
    return _export(_scenario(end_flow=True))[1]


def test_flow_on_end_date_auditor_independent_value():
    result = auditor.audit(_end_flow_export())
    # Last subperiod: 3050 -> 3300 with a 100 deposit on the end date.
    expected = (1 + 20 / 2000) * (1 + 10 / 2520) * (1 + 20 / 3030) * (1 + 150 / 3050) - 1
    assert result["twr"]["twr_pct"] == pytest.approx(expected * 100, abs=1e-6)
    # MWR handles the end-date flow consistently.
    assert result["rows"][1]["ok"] is True


def test_flow_on_end_date_service_twr_matches_auditor():
    export = _end_flow_export()
    result = auditor.audit(export)
    assert result["rows"][0]["auditor"] == pytest.approx(export["service_results"]["twr"]["twr_pct"], abs=0.01)


def test_mcp_aggregate_audit_tool_is_registered_and_scoped():
    tool = AGGREGATE_TOOLS["get_aggregate_performance_audit"]
    assert tool.heavy is True
    assert "get_aggregate_performance_audit" in mcp_tools.HEAVY_TOOLS
    assert "get_aggregate_performance_audit" in mcp_tools.EXPOSED_TOOL_NAMES
    assert "get_aggregate_performance_audit" in FRESHNESS_TOOLS
    assert "sola lettura" in tool.description

    # The MCP window is the last year from today: data relative to today.
    shift = date.today() - timedelta(days=200) - START
    repo = _scenario(shift=shift)
    deps = mcp_tools.ToolDependencies(repo=repo, performance_service=PerformanceService(repo))
    out = mcp_tools.run_tool_sync(deps, "get_aggregate_performance_audit", {"portfolio_ids": [1, 2]}, USER)

    assert out["portfolio_ids"] == [1, 2] and out["base_currency"] == "EUR"
    assert out["period"] == "1y" and out["start_date"] == (START + shift).isoformat()
    assert out["total_flows"] == 6 and out["consistency_check"]["flows_match_service"] is True
    assert out["service_results"]["source"] == "get_performance_summary"
    assert "data_freshness" in out
    assert auditor.audit(out)["ok"] is True

    with pytest.raises(mcp_tools.McpToolError):
        mcp_tools.run_tool_sync(deps, "get_aggregate_performance_audit", {"portfolio_ids": [1, 2]}, "intruder")
    with pytest.raises(mcp_tools.McpToolError):
        mcp_tools.run_tool_sync(deps, "get_aggregate_performance_audit",
                                {"portfolio_ids": [1, 2], "period": "1y"}, USER)
