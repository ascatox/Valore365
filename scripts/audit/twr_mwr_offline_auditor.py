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
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _load_offline_returns():
    """The recomputation lives in src/backend/app/services/auditor/offline_returns.py
    (TASK-77, shared with the Auditor rule D-PERF-RECOMPUTE). Loaded by file path,
    relative to this script, so the script keeps working without the backend
    dependencies and without importing the app package (``app/__init__`` loads
    the FastAPI application)."""
    path = Path(__file__).resolve().parents[2] / "src" / "backend" / "app" / "services" / "auditor" / "offline_returns.py"
    name = "_valore365_offline_returns"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_offline = _load_offline_returns()
DEFAULT_TOLERANCE_PP = _offline.DEFAULT_TOLERANCE_PP
RATE_LOW = _offline.RATE_LOW
RATE_HIGH = _offline.RATE_HIGH
_d = _offline._d
valuations = _offline.valuations
net_flows = _offline.net_flows
compute_twr = _offline.compute_twr
xirr_cashflows = _offline.xirr_cashflows
npv = _offline.npv
rate_grid = _offline.rate_grid
find_brackets = _offline.find_brackets
bisect = _offline.bisect
compute_xirr = _offline.compute_xirr
service_rate_from_mwr_pct = _offline.service_rate_from_mwr_pct
audit = _offline.audit


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
