#!/usr/bin/env python3
"""Offline TWR / XIRR auditor for the Valore365 performance audit export (TASK-PERF-02).

Standalone (standard library only, no app imports). Reads the JSON produced by
``build_performance_audit_export`` / the MCP tool ``get_aggregate_performance_audit``
(from a file path or stdin), recomputes:

- TWR: product of the sub-period returns between consecutive flow dates,
  r_i = (V_i - V_{i-1} - CF_i) / V_{i-1}, using ``valuation_on_flow_dates``
  (end-of-day values) and the net flows of ``net_flows_by_date`` with
  ``in_twr_mwr`` true. Flows on the start day are inside the start value.
  Like the service, when the start value is <= 0 the chain starts on the
  first day with a positive net flow.
- XIRR: own bisection on the NPV, ACT/365, investor perspective
  (-start value, -deposits, +withdrawals, +end value), converted into the
  period return (1 + r) ** (days / 365) - 1.

It prints a comparison table against ``service_results`` (deltas in
percentage points and the NPV residual of both rates), flags possible
multiple IRR roots (NPV sign changes on a rate grid), and exits with code 1
when any |delta| exceeds the tolerance (default 0.01 pp).

Usage:
    python scripts/audit/twr_mwr_offline_auditor.py export.json
    cat export.json | python scripts/audit/twr_mwr_offline_auditor.py -
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from typing import Any

DEFAULT_TOLERANCE_PP = 0.01
RATE_LOW = -0.99
RATE_HIGH = 1000.0


def _d(value: str) -> date:
    return date.fromisoformat(value)


def valuations(export: dict[str, Any]) -> dict[date, float | None]:
    out: dict[date, float | None] = {}
    for row in export.get("valuation_on_flow_dates", []):
        v = row.get("value_eur")
        out[_d(row["date"])] = float(v) if v is not None else None
    return out


def net_flows(export: dict[str, Any]) -> dict[date, float]:
    """Net flow per date, portfolio perspective (+ money in), every flow of the window."""
    out: dict[date, float] = {}
    for row in export.get("net_flows_by_date", []):
        day = _d(row["date"])
        out[day] = out.get(day, 0.0) + float(row["amount_eur"])
    return out


def compute_twr(export: dict[str, Any]) -> dict[str, Any]:
    """Independent TWR (period %, None if not computable)."""
    start, end = _d(export["start_date"]), _d(export["end_date"])
    values = valuations(export)
    flows = net_flows(export)
    v_start = values.get(start)
    if v_start is None or v_start <= 0:
        first_in = next((d for d in sorted(flows) if start <= d <= end and flows[d] > 0), None)
        if first_in is not None:
            start = first_in
            v_start = values.get(start)
    if v_start is None or v_start <= 0:
        return {"twr_pct": None, "start_date": start.isoformat(), "subperiods": []}

    boundaries = sorted(d for d in flows if start < d <= end)
    if not boundaries or boundaries[-1] != end:
        boundaries.append(end)
    linked = 1.0
    prev_value = v_start
    prev_day = start
    subperiods = []
    for day in boundaries:
        value = values.get(day)
        if value is None:
            return {"twr_pct": None, "start_date": start.isoformat(), "subperiods": subperiods,
                    "error": f"valutazione mancante al {day.isoformat()}"}
        cf = flows.get(day, 0.0)
        if prev_value > 0:
            r = (value - prev_value - cf) / prev_value
            linked *= 1.0 + r
            subperiods.append({"from": prev_day.isoformat(), "to": day.isoformat(), "flow": cf, "return": r})
        prev_value, prev_day = value, day
    return {"twr_pct": (linked - 1.0) * 100.0, "start_date": start.isoformat(), "subperiods": subperiods}


def xirr_cashflows(export: dict[str, Any]) -> list[tuple[float, float]]:
    """(years from start ACT/365, investor amount) for the window."""
    start, end = _d(export["start_date"]), _d(export["end_date"])
    values = valuations(export)
    out: list[tuple[float, float]] = []
    v_start = values.get(start) or 0.0
    if v_start != 0:
        out.append((0.0, -v_start))
    for day, amount in sorted(net_flows(export).items()):
        if start < day <= end and amount != 0:
            out.append(((day - start).days / 365.0, -amount))
    out.append(((end - start).days / 365.0, float(values.get(end) or 0.0)))
    return out


def npv(rate: float, cashflows: list[tuple[float, float]]) -> float:
    if rate <= -1.0:
        return math.inf
    return sum(cf / (1.0 + rate) ** t for t, cf in cashflows)


def rate_grid(low: float = RATE_LOW, high: float = RATE_HIGH) -> list[float]:
    grid = [low + i * 0.01 for i in range(int((min(high, 1.0) - low) / 0.01) + 1)]
    x = 1.0
    while x < high:
        x *= 1.1
        grid.append(min(x, high))
    return sorted(set(grid))


def find_brackets(cashflows: list[tuple[float, float]], grid: list[float] | None = None) -> list[tuple[float, float]]:
    """Intervals of the grid where the NPV changes sign (each holds a root)."""
    grid = grid or rate_grid()
    brackets = []
    prev_x, prev_f = grid[0], npv(grid[0], cashflows)
    for x in grid[1:]:
        f = npv(x, cashflows)
        if math.isfinite(prev_f) and math.isfinite(f):
            if prev_f == 0:
                brackets.append((prev_x, prev_x))
            elif prev_f * f < 0:
                brackets.append((prev_x, x))
        prev_x, prev_f = x, f
    if math.isfinite(prev_f) and prev_f == 0:
        brackets.append((prev_x, prev_x))
    return brackets


def bisect(cashflows: list[tuple[float, float]], low: float, high: float, iterations: int = 300) -> float:
    if low == high:
        return low
    f_low = npv(low, cashflows)
    for _ in range(iterations):
        mid = (low + high) / 2.0
        f_mid = npv(mid, cashflows)
        if f_mid == 0 or (high - low) < 1e-15:
            return mid
        if f_low * f_mid < 0:
            high = mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2.0


def compute_xirr(export: dict[str, Any]) -> dict[str, Any]:
    """Independent XIRR: annual rate, period %, roots found, NPV residual."""
    start, end = _d(export["start_date"]), _d(export["end_date"])
    days = max((end - start).days, 1)
    cashflows = xirr_cashflows(export)
    if not (any(cf > 0 for _, cf in cashflows) and any(cf < 0 for _, cf in cashflows)):
        return {"annual_rate": None, "mwr_pct": None, "roots": [], "multiple_roots": False,
                "npv_residual": None, "cashflows": cashflows}
    roots = [bisect(cashflows, lo, hi) for lo, hi in find_brackets(cashflows)]
    if not roots:
        return {"annual_rate": None, "mwr_pct": None, "roots": [], "multiple_roots": False,
                "npv_residual": None, "cashflows": cashflows}
    # Several roots: report them all, use the one closest to 0 (most plausible).
    rate = min(roots, key=abs)
    return {
        "annual_rate": rate,
        "mwr_pct": ((1.0 + rate) ** (days / 365.0) - 1.0) * 100.0,
        "roots": roots,
        "multiple_roots": len(roots) > 1,
        "npv_residual": npv(rate, cashflows),
        "cashflows": cashflows,
    }


def service_rate_from_mwr_pct(mwr_pct: float | None, days: int) -> float | None:
    if mwr_pct is None:
        return None
    base = 1.0 + mwr_pct / 100.0
    if base <= 0:
        return None
    return base ** (365.0 / max(days, 1)) - 1.0


def audit(export: dict[str, Any], tolerance_pp: float = DEFAULT_TOLERANCE_PP) -> dict[str, Any]:
    service = export.get("service_results") or {}
    s_twr = (service.get("twr") or {}).get("twr_pct")
    s_mwr = (service.get("mwr") or {}).get("mwr_pct")
    twr = compute_twr(export)
    xirr = compute_xirr(export)
    days = max((_d(export["end_date"]) - _d(export["start_date"])).days, 1)
    s_rate = service_rate_from_mwr_pct(s_mwr, days)

    def row(name: str, service_value: float | None, auditor_value: float | None) -> dict[str, Any]:
        if service_value is None or auditor_value is None:
            delta = None
            ok = service_value is None and auditor_value is None
        else:
            delta = auditor_value - service_value
            ok = abs(delta) <= tolerance_pp
        return {"metric": name, "service": service_value, "auditor": auditor_value, "delta_pp": delta, "ok": ok}

    rows = [row("TWR %", s_twr, twr["twr_pct"]), row("MWR % (period)", s_mwr, xirr["mwr_pct"])]
    return {
        "rows": rows,
        "ok": all(r["ok"] for r in rows),
        "tolerance_pp": tolerance_pp,
        "twr": twr,
        "xirr": xirr,
        "service_annual_rate": s_rate,
        "service_npv_residual": npv(s_rate, xirr["cashflows"]) if s_rate is not None else None,
    }


def _fmt(value: float | None, digits: int = 4) -> str:
    return "n/d" if value is None else f"{value:.{digits}f}"


def format_report(result: dict[str, Any], export: dict[str, Any]) -> str:
    lines = [
        f"Portafogli {export.get('portfolio_ids')}  periodo {export.get('period')}  "
        f"{export.get('start_date')} -> {export.get('end_date')}",
        f"{'metrica':<16}{'servizio':>14}{'auditor':>14}{'delta pp':>12}  esito",
    ]
    for r in result["rows"]:
        lines.append(
            f"{r['metric']:<16}{_fmt(r['service']):>14}{_fmt(r['auditor']):>14}"
            f"{_fmt(r['delta_pp']):>12}  {'OK' if r['ok'] else 'DIFF'}"
        )
    x = result["xirr"]
    lines.append(f"XIRR annuo auditor: {_fmt(x['annual_rate'], 8)}  residuo NPV: {_fmt(x['npv_residual'], 6)}")
    lines.append(
        f"XIRR annuo servizio (da mwr_pct): {_fmt(result['service_annual_rate'], 8)}  "
        f"residuo NPV: {_fmt(result['service_npv_residual'], 6)}"
    )
    if x["multiple_roots"]:
        lines.append("ATTENZIONE: radici multiple dell'NPV: " + ", ".join(_fmt(r, 6) for r in x["roots"]))
    lines.append(f"Tolleranza {result['tolerance_pp']} pp: {'OK' if result['ok'] else 'DISCREPANZA'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("export", nargs="?", default="-", help="file JSON dell'export, '-' per stdin")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_PP, help="tolleranza in punti percentuali")
    parser.add_argument("--json", action="store_true", help="stampa il risultato in JSON")
    args = parser.parse_args(argv)
    if args.export == "-":
        export = json.load(sys.stdin)
    else:
        with open(args.export, encoding="utf-8") as fh:
            export = json.load(fh)
    result = audit(export, args.tolerance)
    if args.json:
        print(json.dumps(result, default=str, indent=2))
    else:
        print(format_report(result, export))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
