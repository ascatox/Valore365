"""Auditor, gruppo D: coerenza fra tool, vista aggregata e dati (TASK-77).

Contratto: ``docs/auditor/architecture.md`` (dichiarazione ``RULES``, ``check(ctx, scope)``,
esiti, evidenze, scope, argomenti canonici, letture dirette) e ``docs/auditor/rules.md`` §5
(schede, tolleranze di §0.2, comportamenti comuni di §0.3).

Le regole sono funzioni pure sul contesto: leggono solo ``ctx.scoped`` / ``ctx.call`` /
``ctx.try_call`` / ``ctx.transactions`` / ``ctx.performance_audit`` e non catturano le
eccezioni dei tool (le trasforma il motore). Nessun import dal motore dell'Auditor: solo
libreria standard, ``app.copilot_doctor_tools`` (messaggio costante di funzione disattivata)
e ``app.services.auditor.offline_returns`` (ricalcolo indipendente di TWR e XIRR).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# Costanti (rules.md §0.2)
# ---------------------------------------------------------------------------

EPS = 1e-9
T_EUR = 0.01
T_PP = 0.005
T_PP2 = 0.02
# Una percentuale arrotondata a 1 decimale (0,05) confrontata con una a 2 decimali (0,005):
# get_portfolio_health.max_position_weight è round(x, 1) in compute_max_position_weight
# (portfolio_doctor/_health.py). TASK-79, vedi architecture.md «Deviazioni».
T_PP1 = 0.055
T_RET = 0.01
R_PX_MIN = 1.0 / 20.0
R_PX_MAX = 20.0
MAX_POSITION_ROWS = 30  # get_positions restituisce al più 30 righe
CASH_BREAKDOWN_TOLERANCE = 0.06
TER_MATCH_TOLERANCE = 0.01
XRAY_STATUS_TOLERANCE = 0.05
GLOBAL_EQUITY_CRASH = "Global Equity Crash"
SAME_ISIN_NOTE = "Stesso strumento (ISIN)"

# Copia di app.repository._utilities.CASH_COMPONENT_SIGNS (il modulo delle regole non può
# importare il repository, architettura §3.2).
CASH_COMPONENT_SIGNS: dict[str, int] = {
    "opening_balance": 1,
    "deposits": 1,
    "withdrawals": -1,
    "dividends": 1,
    "interest": 1,
    "fees": -1,
    "buys": -1,
    "sells": 1,
    "implicit_contributions": 1,
}

CASH_SIDES = frozenset({"deposit", "withdrawal", "dividend", "fee", "interest"})
TRADE_SIDES = frozenset({"buy", "sell"})
# Soglie della deduplica (app.services.csv_service: DUPLICATE_REL/ABS_TOLERANCE).
DUP_REL_TOLERANCE = 1e-6
DUP_ABS_TOLERANCE = 1e-8
LSE_CURRENCIES = frozenset({"GBP", "GBp", "GBX", "USD"})

AGGREGATE_TOOL_OF: dict[str, str] = {
    "get_portfolio_summary": "get_aggregate_summary",
    "get_positions": "get_aggregate_positions",
    "get_performance": "get_aggregate_performance",
    "get_portfolio_health": "get_aggregate_health",
    "get_stress_test": "get_aggregate_stress_test",
    "get_xray_summary": "get_aggregate_xray",
}
TRANSACTIONS_TOOL = "ctx.transactions"
PERFORMANCE_AUDIT_TOOL = "ctx.performance_audit"


def t_sum_eur(n: int) -> float:
    return 0.005 * n + 0.01


def t_w(n: int) -> float:
    return max(0.05, 0.005 * n)


# ---------------------------------------------------------------------------
# Esiti ed evidenze (architettura §3.3)
# ---------------------------------------------------------------------------


def _ev(
    tool: str, args: Mapping[str, Any], path: str, observed: Any, expected: Any = None,
    tolerance: float | None = None, note: str | None = None,
) -> dict[str, Any]:
    return {
        "tool": tool, "args": dict(args), "path": path, "observed": observed,
        "expected": expected, "tolerance": tolerance, "note": note,
    }


def _pass(evidence: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    return {"status": "pass", "reason_code": None, "reason": None, "evidence": list(evidence)}


def _fail(reason: str, evidence: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "fail", "reason_code": "invariant_violated", "reason": reason, "evidence": list(evidence)}


def _skip(code: str, reason: str, evidence: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    return {"status": "skip", "reason_code": code, "reason": reason, "evidence": list(evidence)}


def _judge(failures: list[dict[str, Any]], reason: str, passed: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    return _fail(reason, failures) if failures else _pass(passed)


def _r(value: Any, digits: int = 6) -> Any:
    return round(value, digits) if isinstance(value, float) else value


# ---------------------------------------------------------------------------
# Scope e letture comuni
# ---------------------------------------------------------------------------


def _scope_ids(scope: Mapping[str, Any]) -> list[int]:
    if scope["kind"] in ("aggregate", "user"):
        return [int(i) for i in scope["portfolio_ids"]]
    return [int(scope["portfolio_id"])]


def _scoped_args(tool: str, scope: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> tuple[str, dict]:
    """Nome e argomenti effettivi di ``ctx.scoped(tool, scope, extra)`` (per le evidenze)."""
    if scope["kind"] == "aggregate":
        return AGGREGATE_TOOL_OF[tool], {"portfolio_ids": list(scope["portfolio_ids"])}
    return tool, {"portfolio_id": scope["portfolio_id"], **dict(extra or {})}


def _read(ctx: Any, tool: str, scope: Mapping[str, Any], extra: Mapping[str, Any] | None = None):
    name, args = _scoped_args(tool, scope, extra)
    return ctx.scoped(tool, scope, extra), name, args


def _positions(ctx: Any, scope: Mapping[str, Any]) -> tuple[dict, list[dict], str, dict]:
    out, name, args = _read(ctx, "get_positions", scope)
    return out, list(out.get("positions") or []), name, args


def _is_truncated(scope: Mapping[str, Any], out: Mapping[str, Any], rows: Sequence[Any]) -> bool:
    if scope["kind"] == "aggregate":
        count = out.get("positions_count")
        return isinstance(count, int) and count > len(rows)
    return len(rows) >= MAX_POSITION_ROWS


def _position_count(scope: Mapping[str, Any], out: Mapping[str, Any], rows: Sequence[Any]) -> int:
    if scope["kind"] == "aggregate" and isinstance(out.get("positions_count"), int):
        return int(out["positions_count"])
    return len(rows)


def _empty_skip(name: str, args: dict) -> dict[str, Any]:
    return _skip("empty_portfolio", "Nessuna posizione in portafoglio: niente da verificare.",
                 [_ev(name, args, "positions", [], None, None, "nessuna riga")])


def _truncated_skip(name: str, args: dict, rows: int, count: Any) -> dict[str, Any]:
    return _skip(
        "truncated_output",
        "L'elenco delle posizioni è limitato a 30 righe: la somma non è verificabile.",
        [_ev(name, args, "positions", rows, count, None, "righe restituite / posizioni totali")],
    )


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _no_transactions(ctx: Any, ids: Sequence[int]) -> tuple[bool, list[int], list[dict]]:
    """(tutti senza transazioni, id con transazioni, evidenze) — rules.md §0.3."""
    with_tx: list[int] = []
    evidence: list[dict] = []
    for pid in ids:
        rows = ctx.transactions(pid)
        if rows:
            with_tx.append(pid)
        else:
            evidence.append(_ev(TRANSACTIONS_TOOL, {"portfolio_id": pid}, "[*]", 0, None, None, "numero di transazioni"))
    return not with_tx, with_tx, evidence


def _no_tx_skip(evidence: list[dict]) -> dict[str, Any]:
    return _skip("no_transactions", "Nessuna transazione: rendimenti e valore storico non sono verificabili.", evidence)


def _perf_args(ids: Sequence[int]) -> dict[str, Any]:
    return {"portfolio_ids": sorted(int(i) for i in ids)}


def _doctor_metrics(ctx: Any, pid: int) -> dict[str, Any] | None:
    """read_doctor_metrics senza metric_codes; None se la funzione è spenta (§0.3)."""
    args = {"portfolio_id": pid}
    attempt = ctx.try_call("read_doctor_metrics", args)
    if attempt["ok"]:
        return attempt["result"]
    if _is_policy_disabled(attempt.get("error")):
        return None
    # Errore inatteso: lo si lascia salire (il motore lo trasforma in error/tool_error).
    return ctx.call("read_doctor_metrics", args)


def _is_policy_disabled(message: Any) -> bool:
    if not isinstance(message, str):
        return False
    try:
        from app.copilot_doctor_tools import POLICY_DISABLED_MESSAGE
    except Exception:  # pragma: no cover - import difensivo
        POLICY_DISABLED_MESSAGE = "Funzione disattivata (feature_disabled): le policy del Portfolio Doctor"
    return message.strip() == POLICY_DISABLED_MESSAGE.strip() or message.startswith(POLICY_DISABLED_MESSAGE[:60])


def _disabled_skip(pid: int) -> dict[str, Any]:
    return _skip("feature_disabled", "Le metriche del Doctor sono disattivate da configurazione.",
                 [_ev("read_doctor_metrics", {"portfolio_id": pid}, "error", "feature_disabled")])


def _metric(metrics: Mapping[str, Any], code: str) -> dict[str, Any] | None:
    for row in metrics.get("metrics") or []:
        if row.get("code") == code:
            return row
    return None


# ---------------------------------------------------------------------------
# D-WEIGHTS-SUM
# ---------------------------------------------------------------------------


def check_weights_sum(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    out, rows, name, args = _positions(ctx, scope)
    if not rows:
        return _empty_skip(name, args)
    if _is_truncated(scope, out, rows):
        return _truncated_skip(name, args, len(rows), _position_count(scope, out, rows))
    n = len(rows)
    total = sum(float(r.get("weight") or 0.0) for r in rows)
    tol = t_w(n)
    ev = _ev(name, args, "positions[*].weight", _r(total), 100.0, tol, f"somma di {n} pesi")
    if abs(total - 100.0) > tol + EPS:
        return _fail(f"I pesi delle posizioni sommano a {total:.2f} invece di 100.", [ev])
    return _pass([ev])


# ---------------------------------------------------------------------------
# D-SUMMARY-POSITIONS
# ---------------------------------------------------------------------------


def check_summary_positions(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    summary, s_name, s_args = _read(ctx, "get_portfolio_summary", scope)
    out, rows, p_name, p_args = _positions(ctx, scope)
    if not rows:
        return _empty_skip(p_name, p_args)
    if _is_truncated(scope, out, rows):
        return _truncated_skip(p_name, p_args, len(rows), _position_count(scope, out, rows))
    n = len(rows)
    tol = t_sum_eur(n)
    failures: list[dict] = []
    passed: list[dict] = []
    for field in ("market_value", "cost_basis"):
        observed = _num(summary.get(field))
        expected = sum(float(r.get(field) or 0.0) for r in rows)
        evs = [
            _ev(s_name, s_args, field, observed, _r(expected), tol),
            _ev(p_name, p_args, f"positions[*].{field}", _r(expected), None, None, f"somma di {n} righe"),
        ]
        if observed is None or abs(observed - expected) > tol + EPS:
            failures.extend(evs)
        else:
            passed.append(evs[0])
    mv, cb, pl = (_num(summary.get(k)) for k in ("market_value", "cost_basis", "unrealized_pl"))
    if None in (mv, cb, pl):
        failures.append(_ev(s_name, s_args, "unrealized_pl", pl, None, 0.02, "campo mancante"))
    else:
        ev = _ev(s_name, s_args, "unrealized_pl", pl, _r(mv - cb), 0.02, "market_value − cost_basis")
        (failures if abs(pl - (mv - cb)) > 0.02 + EPS else passed).append(ev)
    return _judge(failures, "Il riepilogo non coincide con la somma delle posizioni.", passed)


# ---------------------------------------------------------------------------
# D-POSITION-VALUE-PRICE
# ---------------------------------------------------------------------------


def check_position_value_price(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    _out, rows, name, args = _positions(ctx, scope)
    if not rows:
        return _empty_skip(name, args)
    failures: list[dict] = []
    for row in rows:
        mv = float(row.get("market_value") or 0.0)
        qty = float(row.get("quantity") or 0.0)
        px = float(row.get("market_price") or 0.0)
        tol = T_EUR + abs(qty) * 0.00005 + 1e-6 * abs(mv)
        if abs(mv - qty * px) > tol + EPS:
            failures.append(_ev(name, args, f"positions[symbol={row.get('symbol')}].market_value", mv,
                                _r(qty * px), _r(tol), "quantity × market_price"))
    return _judge(failures, "Il valore di almeno una posizione non è quantità per prezzo.",
                  [_ev(name, args, "positions[*]", len(rows), None, None, "righe verificate")])


# ---------------------------------------------------------------------------
# D-CASH-CONSISTENCY
# ---------------------------------------------------------------------------


def check_cash_consistency(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    args = {"portfolio_id": scope["portfolio_id"]}
    summary = ctx.scoped("get_portfolio_summary", scope)
    cash = ctx.scoped("get_cash_balance", scope)
    failures: list[dict] = []
    passed: list[dict] = []
    total_cash = _num(cash.get("total_cash"))

    def compare(s_field: str, c_field: str, tol: float) -> None:
        s_val, c_val = _num(summary.get(s_field)), _num(cash.get(c_field))
        evs = [_ev("get_portfolio_summary", args, s_field, s_val, c_val, tol),
               _ev("get_cash_balance", args, c_field, c_val, s_val, tol)]
        if s_val is None or c_val is None or abs(s_val - c_val) > tol + EPS:
            failures.extend(evs)
        else:
            passed.append(evs[0])

    compare("cash_balance", "total_cash", T_EUR)
    compare("implicit_contributions_total", "implicit_contributions_total", T_EUR)
    if total_cash is None or total_cash < -EPS:
        failures.append(_ev("get_cash_balance", args, "total_cash", total_cash, ">= 0"))
    breakdown = cash.get("cash_breakdown") or {}
    unknown = sorted(k for k in breakdown if k not in CASH_COMPONENT_SIGNS)
    for key in unknown:
        failures.append(_ev("get_cash_balance", args, f"cash_breakdown.{key}", breakdown[key], None, None,
                            "componente sconosciuta"))
    folded = sum(CASH_COMPONENT_SIGNS[k] * float(v or 0.0) for k, v in breakdown.items() if k in CASH_COMPONENT_SIGNS)
    ev = _ev("get_cash_balance", args, "cash_breakdown[*]", _r(folded), total_cash, CASH_BREAKDOWN_TOLERANCE,
             "somma con segno delle componenti")
    if total_cash is None or abs(folded - total_cash) > CASH_BREAKDOWN_TOLERANCE + EPS:
        failures.append(ev)
    else:
        passed.append(ev)
    return _judge(failures, "La liquidità del riepilogo e del saldo di cassa non coincide o non torna.", passed)


# ---------------------------------------------------------------------------
# D-SUMMARY-PERFORMANCE-VALUE
# ---------------------------------------------------------------------------


def check_summary_performance_value(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    ids = _scope_ids(scope)
    none_tx, _with, tx_ev = _no_transactions(ctx, ids)
    if none_tx:
        return _no_tx_skip(tx_ev)
    summary, s_name, s_args = _read(ctx, "get_portfolio_summary", scope)
    out, rows, _p_name, _p_args = _positions(ctx, scope)
    export = ctx.performance_audit(ids)
    n = _position_count(scope, out, rows)
    value = _num((export.get("service_results") or {}).get("current_value"))
    mv, cash = _num(summary.get("market_value")), _num(summary.get("cash_balance"))
    total = (mv or 0.0) + (cash or 0.0)
    perf_args = _perf_args(ids)
    if value is None or mv is None or cash is None:
        return _fail("Valore del riepilogo o della performance mancante.", [
            _ev(s_name, s_args, "market_value + cash_balance", _r(total) if mv is not None else None, value),
            _ev(PERFORMANCE_AUDIT_TOOL, perf_args, "service_results.current_value", value, None),
        ])
    tol = 0.005 * (n + 2) + 1e-6 * abs(value)
    evs = [
        _ev(s_name, s_args, "market_value + cash_balance", _r(total), _r(value), _r(tol),
            f"market_value {mv} + cash_balance {cash}"),
        _ev(PERFORMANCE_AUDIT_TOOL, perf_args, "service_results.current_value", _r(value), _r(total), _r(tol)),
    ]
    if abs(total - value) > tol + EPS:
        return _fail("Il valore totale del riepilogo è diverso dall'ultimo valore usato per i rendimenti.", evs)
    return _pass(evs)


# ---------------------------------------------------------------------------
# D-AGG-SUMS
# ---------------------------------------------------------------------------

AGG_SUM_FIELDS = ("market_value", "cost_basis", "cash_balance", "implicit_contributions_total")


def check_agg_sums(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    ids = _scope_ids(scope)
    agg_args = {"portfolio_ids": ids}
    agg = ctx.call("get_aggregate_summary", agg_args)
    singles = {pid: ctx.call("get_portfolio_summary", {"portfolio_id": pid}) for pid in ids}
    k = len(ids)
    tol = t_sum_eur(k)
    failures: list[dict] = []
    passed: list[dict] = []
    for field in AGG_SUM_FIELDS:
        observed = _num(agg.get(field))
        expected = sum(float(s.get(field) or 0.0) for s in singles.values())
        ev = _ev("get_aggregate_summary", agg_args, field, observed, _r(expected), tol,
                 f"somma di get_portfolio_summary.{field} su {k} portafogli")
        if observed is None or abs(observed - expected) > tol + EPS:
            failures.append(ev)
            failures.extend(
                _ev("get_portfolio_summary", {"portfolio_id": pid}, field, s.get(field)) for pid, s in singles.items()
            )
        else:
            passed.append(ev)
    agg_ids = agg.get("portfolio_ids")
    if not isinstance(agg_ids, list) or sorted(int(i) for i in agg_ids) != sorted(ids):
        failures.append(_ev("get_aggregate_summary", agg_args, "portfolio_ids", agg_ids, ids))
    return _judge(failures, "La vista aggregata non è la somma dei portafogli che la compongono.", passed)


# ---------------------------------------------------------------------------
# D-AGG-POSITIONS
# ---------------------------------------------------------------------------


def check_agg_positions(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    ids = _scope_ids(scope)
    agg_args = {"portfolio_ids": ids}
    agg = ctx.call("get_aggregate_positions", agg_args)
    agg_rows = list(agg.get("positions") or [])
    if not agg_rows:
        return _empty_skip("get_aggregate_positions", agg_args)
    k = len(ids)
    singles: dict[int, list[dict]] = {}
    truncated_single: set[int] = set()
    for pid in ids:
        rows = list(ctx.call("get_positions", {"portfolio_id": pid}).get("positions") or [])
        singles[pid] = rows
        if len(rows) >= MAX_POSITION_ROWS:
            truncated_single.add(pid)
    tol_eur = t_sum_eur(k)
    tol_qty = 1e-6 * k
    failures: list[dict] = []
    unverifiable: list[dict] = []
    verified = 0
    for idx, row in enumerate(agg_rows):
        symbol = row.get("symbol")
        matches = {pid: [r for r in rows if r.get("symbol") == symbol] for pid, rows in singles.items()}
        missing_in_truncated = [pid for pid in truncated_single if not matches[pid]]
        if missing_in_truncated:
            unverifiable.append(_ev("get_positions", {"portfolio_id": missing_in_truncated[0]}, "positions",
                                    MAX_POSITION_ROWS, None, None,
                                    f"{symbol}: righe troncate, simbolo non trovato"))
            continue
        verified += 1
        sum_mv = sum(float(r.get("market_value") or 0.0) for rs in matches.values() for r in rs)
        sum_qty = sum(float(r.get("quantity") or 0.0) for rs in matches.values() for r in rs)
        path = f"positions[symbol={symbol}]"
        mv = float(row.get("market_value") or 0.0)
        qty = float(row.get("quantity") or 0.0)
        if abs(mv - sum_mv) > tol_eur + EPS:
            failures.append(_ev("get_aggregate_positions", agg_args, f"{path}.market_value", mv, _r(sum_mv), tol_eur,
                                "somma delle righe dei singoli con lo stesso simbolo"))
        if abs(qty - sum_qty) > tol_qty + EPS:
            failures.append(_ev("get_aggregate_positions", agg_args, f"{path}.quantity", qty, _r(sum_qty, 8), tol_qty,
                                "somma delle quantità dei singoli"))
        duplicates = [r for r in agg_rows if r.get("symbol") == symbol]
        if len(duplicates) > 1 and agg_rows.index(duplicates[0]) == idx:
            failures.append(_ev("get_aggregate_positions", agg_args, path, len(duplicates), 1, None,
                                "righe dello stesso strumento non unite"))
    any_truncated = bool(truncated_single) or _is_truncated(scope, agg, agg_rows)
    if not any_truncated:
        distinct = {r.get("symbol") for rows in singles.values() for r in rows}
        count = agg.get("positions_count")
        ev = _ev("get_aggregate_positions", agg_args, "positions_count", count, len(distinct), None,
                 "simboli distinti fra i singoli")
        if count != len(distinct):
            failures.append(ev)
    if failures:
        return _fail("Le posizioni della vista aggregata non uniscono quelle dei singoli portafogli.", failures)
    if verified == 0:
        return _skip("truncated_output", "Posizioni dei singoli troncate: l'unione non è verificabile.", unverifiable)
    return _pass([_ev("get_aggregate_positions", agg_args, "positions[*]", verified, None, None, "righe verificate")]
                 + unverifiable)


# ---------------------------------------------------------------------------
# D-AGG-PERFORMANCE-VALUE
# ---------------------------------------------------------------------------


def check_agg_performance_value(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    ids = _scope_ids(scope)
    none_tx, with_tx, tx_ev = _no_transactions(ctx, ids)
    if none_tx:
        return _no_tx_skip(tx_ev)
    agg = ctx.performance_audit(ids)
    agg_args = _perf_args(ids)
    agg_value = _num((agg.get("service_results") or {}).get("current_value"))
    singles = {pid: ctx.performance_audit([pid]) for pid in with_tx}
    total = 0.0
    failures: list[dict] = []
    evidence: list[dict] = []
    for pid, export in singles.items():
        value = _num((export.get("service_results") or {}).get("current_value"))
        if value is None:
            failures.append(_ev(PERFORMANCE_AUDIT_TOOL, {"portfolio_ids": [pid]}, "service_results.current_value", None))
            continue
        total += value
        evidence.append(_ev(PERFORMANCE_AUDIT_TOOL, {"portfolio_ids": [pid]}, "service_results.current_value", value))
        if export.get("end_date") != agg.get("end_date"):
            failures.append(_ev(PERFORMANCE_AUDIT_TOOL, {"portfolio_ids": [pid]}, "end_date", export.get("end_date"),
                                agg.get("end_date"), None, "data finale dell'aggregato"))
    k = len(ids)
    tol = t_sum_eur(k)
    ev = _ev(PERFORMANCE_AUDIT_TOOL, agg_args, "service_results.current_value", agg_value, _r(total), tol,
             f"somma dei valori di {len(singles)} portafogli con transazioni (gli altri contano 0)")
    if agg_value is None or abs(agg_value - total) > tol + EPS:
        failures = [ev] + evidence + failures
    if failures:
        return _fail("Il valore finale della performance aggregata non è la somma dei portafogli.", failures)
    return _pass([ev] + evidence)


# ---------------------------------------------------------------------------
# D-PERF-RECOMPUTE
# ---------------------------------------------------------------------------


def check_perf_recompute(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    from app.services.auditor.offline_returns import audit

    ids = _scope_ids(scope)
    none_tx, _with, tx_ev = _no_transactions(ctx, ids)
    if none_tx:
        return _no_tx_skip(tx_ev)
    export = ctx.performance_audit(ids)
    args = _perf_args(ids)
    result = audit(export, tolerance_pp=T_RET)
    failures: list[dict] = []
    passed: list[dict] = []
    paths = {"TWR %": "service_results.twr.twr_pct", "MWR % (period)": "service_results.mwr.mwr_pct"}
    for row in result["rows"]:
        ev = _ev(PERFORMANCE_AUDIT_TOOL, args, paths.get(row["metric"], row["metric"]), _r(row["service"]),
                 _r(row["auditor"]), T_RET, "ricalcolo indipendente (offline_returns.audit)")
        (passed if row["ok"] else failures).append(ev)
    if result.get("ok") is not True and not failures:  # pragma: no cover - difensivo
        failures.append(_ev(PERFORMANCE_AUDIT_TOOL, args, "service_results", False, True, T_RET, "audit non ok"))
    check = export.get("consistency_check") or {}
    for key in ("flows_match_service", "count_match", "totals_match"):
        if check.get(key) is not True:
            failures.append(_ev(PERFORMANCE_AUDIT_TOOL, args, f"consistency_check.{key}", check.get(key), True))
    return _judge(failures, "I rendimenti del servizio non coincidono con il ricalcolo indipendente.", passed)


# ---------------------------------------------------------------------------
# D-PERF-TOOL-MATCH
# ---------------------------------------------------------------------------


def check_perf_tool_match(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    ids = _scope_ids(scope)
    none_tx, _with, tx_ev = _no_transactions(ctx, ids)
    if none_tx:
        return _no_tx_skip(tx_ev)
    perf, name, args = _read(ctx, "get_performance", scope)
    export = ctx.performance_audit(ids)
    service = export.get("service_results") or {}
    pairs = (
        ("twr_1y", _num((service.get("twr") or {}).get("twr_pct")), "service_results.twr.twr_pct"),
        ("mwr_1y", _num((service.get("mwr") or {}).get("mwr_pct")), "service_results.mwr.mwr_pct"),
    )
    failures: list[dict] = []
    passed: list[dict] = []
    for field, raw, path in pairs:
        shown = _num(perf.get(field))
        expected = round(raw, 2) if raw is not None else None
        evs = [_ev(name, args, field, shown, expected, T_PP),
               _ev(PERFORMANCE_AUDIT_TOOL, _perf_args(ids), path, _r(raw), shown, T_PP, "arrotondato a 2 decimali")]
        if shown is None or expected is None:
            ok = shown is None and expected is None
        else:
            ok = abs(shown - expected) <= T_PP + EPS
        (passed if ok else failures).extend(evs if not ok else evs[:1])
    return _judge(failures, "Il rendimento mostrato non è quello calcolato dal servizio.", passed)


# ---------------------------------------------------------------------------
# D-DOCTOR-TER
# ---------------------------------------------------------------------------


def check_doctor_ter(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    pid = scope["portfolio_id"]
    args = {"portfolio_id": pid}
    metrics = _doctor_metrics(ctx, pid)
    if metrics is None:
        return _disabled_skip(pid)
    _out, rows, _name, _pargs = _positions(ctx, scope)
    for row in rows:
        symbol = row.get("symbol")
        info = ctx.scoped("search_asset_info", scope, {"symbol": symbol})
        if str(info.get("type") or "").lower() == "cash":
            return _skip("not_applicable",
                         "Una posizione è liquidità: il Doctor la esclude dal valore investito, i costi no.",
                         [_ev("search_asset_info", {**args, "symbol": symbol}, "type", info.get("type"))])
    metric = _metric(metrics, "weighted_ter_pct") or {}
    health = ctx.scoped("get_portfolio_health", scope)
    costs = ctx.scoped("get_cost_breakdown", scope)
    d = _num(metric.get("value"))
    h = _num(health.get("weighted_ter"))
    c = _num(costs.get("weighted_ter_pct"))
    evs = [
        _ev("read_doctor_metrics", args, "metrics[code=weighted_ter_pct].value", d, c, TER_MATCH_TOLERANCE),
        _ev("get_portfolio_health", args, "weighted_ter", h, c, TER_MATCH_TOLERANCE),
        _ev("get_cost_breakdown", args, "weighted_ter_pct", c, None, None),
    ]
    if d is None or h is None or c is None:
        return _skip("no_reference_data", "TER medio non disponibile in almeno una delle tre analisi.", evs)
    failures = []
    if abs(d - c) > TER_MATCH_TOLERANCE + EPS:
        failures.append(evs[0])
    if abs(h - c) > TER_MATCH_TOLERANCE + EPS:
        failures.append(evs[1])
    if failures:
        return _fail("Il TER medio non è lo stesso nel Doctor, nella salute e nei costi.", failures + [evs[2]])
    return _pass(evs)


# ---------------------------------------------------------------------------
# D-DOCTOR-CLASS-WEIGHTS
# ---------------------------------------------------------------------------


def check_doctor_class_weights(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    pid = scope["portfolio_id"]
    args = {"portfolio_id": pid}
    metrics = _doctor_metrics(ctx, pid)
    if metrics is None:
        return _disabled_skip(pid)
    _out, rows, name, pargs = _positions(ctx, scope)
    if not rows:
        return _empty_skip(name, pargs)
    stress = ctx.scoped("get_stress_test", scope)
    scenario = next((s for s in stress.get("scenarios") or [] if s.get("scenario_name") == GLOBAL_EQUITY_CRASH), None)
    if scenario is None:
        return _fail("Lo scenario «Global Equity Crash» manca dallo stress test.",
                     [_ev("get_stress_test", args, "scenarios[*].scenario_name", None, GLOBAL_EQUITY_CRASH)])
    weights: dict[str, float] = {}
    for row in scenario.get("class_breakdown") or []:
        cls = str(row.get("asset_class"))
        weights[cls] = weights.get(cls, 0.0) + float(row.get("weight_pct") or 0.0)
    invested = 100.0 - weights.get("cash", 0.0)
    if invested <= EPS:
        return _skip("empty_portfolio", "Il portafoglio contiene solo liquidità: nessun valore investito.",
                     [_ev("get_stress_test", args, f"scenarios[scenario_name={GLOBAL_EQUITY_CRASH}].class_breakdown"
                          "[asset_class=cash].weight_pct", weights.get("cash"))])

    def w(cls: str) -> float:
        return weights.get(cls, 0.0) / invested * 100.0

    n = len(rows)
    tol = t_w(n)
    sp = f"scenarios[scenario_name={GLOBAL_EQUITY_CRASH}].class_breakdown[asset_class=%s].weight_pct"
    failures: list[dict] = []
    passed: list[dict] = []

    def lower_of(code: str) -> float | None:
        return _num((_metric(metrics, code) or {}).get("lower"))

    for code, cls in (("equity_weight_pct", "equity"), ("bond_weight_pct", "bond")):
        lower = lower_of(code)
        evs = [_ev("read_doctor_metrics", args, f"metrics[code={code}].lower", lower, _r(w(cls)), tol,
                   "peso dello stress rinormalizzato senza liquidità"),
               _ev("get_stress_test", args, sp % cls, weights.get(cls, 0.0))]
        if lower is None or abs(lower - w(cls)) > tol + EPS:
            failures.extend(evs)
        else:
            passed.append(evs[0])
    gold = lower_of("gold_weight_pct")
    low, high = w("gold") - tol, w("gold") + w("commodity") + tol
    evs = [_ev("read_doctor_metrics", args, "metrics[code=gold_weight_pct].lower", gold,
               [_r(w("gold")), _r(w("gold") + w("commodity"))], tol, "fra oro e oro + materie prime dello stress"),
           _ev("get_stress_test", args, sp % "gold", weights.get("gold", 0.0)),
           _ev("get_stress_test", args, sp % "commodity", weights.get("commodity", 0.0))]
    if gold is None or not (low - EPS <= gold <= high + EPS):
        failures.extend(evs)
    else:
        passed.append(evs[0])
    return _judge(failures, "Le quote per classe del Doctor non coincidono con lo stress test.", passed)


# ---------------------------------------------------------------------------
# D-DOCTOR-CONCENTRATION
# ---------------------------------------------------------------------------


def check_doctor_concentration(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    pid = scope["portfolio_id"]
    args = {"portfolio_id": pid}
    metrics = _doctor_metrics(ctx, pid)
    if metrics is None:
        return _disabled_skip(pid)
    if metrics.get("is_empty"):
        return _skip("empty_portfolio", "Nessuna posizione in portafoglio: niente da verificare.",
                     [_ev("read_doctor_metrics", args, "is_empty", True)])
    metric = _metric(metrics, "max_single_position_pct") or {}
    d = _num(metric.get("value"))
    if d is None:
        return _skip("no_reference_data", "Il Doctor non riporta il peso della posizione più grande.",
                     [_ev("read_doctor_metrics", args, "metrics[code=max_single_position_pct].value", None)])
    health = ctx.scoped("get_portfolio_health", scope)
    h = _num(health.get("max_position_weight"))
    same_isin = any(SAME_ISIN_NOTE in str(n) for n in metric.get("notes") or [])
    evs = [_ev("read_doctor_metrics", args, "metrics[code=max_single_position_pct].value", d, h, T_PP1,
               ">= salute (stesso ISIN aggregato)" if same_isin else None),
           _ev("get_portfolio_health", args, "max_position_weight", h)]
    if h is None:
        return _fail("La salute non riporta il peso della posizione più grande.", evs)
    ok = d >= h - T_PP1 - EPS if same_isin else abs(d - h) <= T_PP1 + EPS
    if not ok:
        return _fail("Il peso della posizione più grande è diverso nel Doctor e nella salute.", evs)
    return _pass(evs)


# ---------------------------------------------------------------------------
# D-DOCTOR-CASH (TASK-84)
# ---------------------------------------------------------------------------

DOCTOR_CASH_SCENARIO: dict[str, Any] = {"mode": "new_cash_only", "new_cash": 100.0}


def _is_simulator_disabled(message: Any) -> bool:
    if not isinstance(message, str):
        return False
    try:
        from app.copilot_doctor_tools import SIMULATOR_DISABLED_MESSAGE
    except Exception:  # pragma: no cover - import difensivo
        SIMULATOR_DISABLED_MESSAGE = "Funzione disattivata (feature_disabled): lo Scenario Lab del Portfolio Doctor"
    return message.strip() == SIMULATOR_DISABLED_MESSAGE.strip() or message.startswith(SIMULATOR_DISABLED_MESSAGE[:60])


def _doctor_scenario_args(scope: Mapping[str, Any]) -> dict[str, Any]:
    """Argomenti di ``ctx.scoped("build_doctor_scenario", scope, DOCTOR_CASH_SCENARIO)``."""
    if scope["kind"] == "aggregate":
        ids = list(scope["portfolio_ids"])
        return {"portfolio_id": ids[0], "portfolio_ids": ids, **DOCTOR_CASH_SCENARIO}
    return {"portfolio_id": scope["portfolio_id"], **DOCTOR_CASH_SCENARIO}


def check_doctor_cash(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    d_args = _doctor_scenario_args(scope)
    attempt = ctx.try_call("build_doctor_scenario", d_args)
    if not attempt["ok"]:
        if _is_simulator_disabled(attempt.get("error")):
            return _skip("feature_disabled", "Lo Scenario Lab del Doctor è disattivato da configurazione.",
                         [_ev("build_doctor_scenario", d_args, "error", "feature_disabled")])
        # Errore inatteso: lo si lascia salire (il motore lo trasforma in error/tool_error).
        ctx.call("build_doctor_scenario", d_args)
    before = (attempt["result"] or {}).get("before")
    if not isinstance(before, dict):
        return _fail("Lo Scenario Lab non riporta la situazione di partenza.",
                     [_ev("build_doctor_scenario", d_args, "before", before)])
    summary, s_name, s_args = _read(ctx, "get_portfolio_summary", scope)

    # Posizioni di tipo liquidità: il Doctor le conta nella liquidità, il riepilogo nel valore.
    cash_rows: list[dict] = []
    for pid in _scope_ids(scope):
        p_args = {"portfolio_id": pid}
        rows = list(ctx.call("get_positions", p_args).get("positions") or [])
        if len(rows) >= MAX_POSITION_ROWS:
            return _truncated_skip("get_positions", p_args, len(rows), None)
        for row in rows:
            info = ctx.call("search_asset_info", {**p_args, "symbol": row.get("symbol")})
            if str(info.get("type") or "").lower() == "cash":
                cash_rows.append(_ev("get_positions", p_args, f"positions[symbol={row.get('symbol')}].market_value",
                                     _num(row.get("market_value")), None, None, "posizione di tipo liquidità"))
    k = sum(float(ev["observed"] or 0.0) for ev in cash_rows)

    c = _num(before.get("cash_value"))
    inv = _num(before.get("invested_value"))
    tot = _num(before.get("total_value"))
    s = _num(summary.get("cash_balance"))
    failures: list[dict] = []
    passed: list[dict] = []

    tol = T_EUR if not cash_rows else t_sum_eur(len(cash_rows) + 1)
    expected = None if s is None else _r(s + k)
    evs = [_ev("build_doctor_scenario", d_args, "before.cash_value", c, expected, tol,
               "liquidità del riepilogo + posizioni di tipo liquidità" if cash_rows else "liquidità del riepilogo"),
           _ev(s_name, s_args, "cash_balance", s)]
    if c is None or s is None or abs(c - (s + k)) > tol + EPS:
        failures.extend(evs + cash_rows)
    else:
        passed.append(evs[0])

    if scope["kind"] == "portfolio":
        cash = ctx.scoped("get_cash_balance", scope)
        total_cash = _num(cash.get("total_cash"))
        evs = [_ev(s_name, s_args, "cash_balance", s, total_cash, T_EUR),
               _ev("get_cash_balance", {"portfolio_id": scope["portfolio_id"]}, "total_cash", total_cash)]
        if s is None or total_cash is None or abs(s - total_cash) > T_EUR + EPS:
            failures.extend(evs)
        else:
            passed.append(evs[0])

    # Tre importi arrotondati a 2 decimali: 0,015 € = T_sum_eur(1).
    tol_total = t_sum_eur(1)
    ev = _ev("build_doctor_scenario", d_args, "before.total_value", tot,
             None if inv is None or c is None else _r(inv + c), tol_total, "invested_value + cash_value")
    if tot is None or inv is None or c is None or abs(tot - (inv + c)) > tol_total + EPS:
        failures.append(ev)
    else:
        passed.append(ev)
    return _judge(failures, "La liquidità vista dal Doctor non è quella del riepilogo.", passed)


# ---------------------------------------------------------------------------
# D-HEALTH-SCORE-BREAKDOWN
# ---------------------------------------------------------------------------


def check_health_score_breakdown(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    _out, rows, p_name, p_args = _positions(ctx, scope)
    if not rows:
        return _empty_skip(p_name, p_args)
    health, name, args = _read(ctx, "get_portfolio_health", scope)
    categories = health.get("category_scores") or {}
    maxima = health.get("category_max_scores") or {}
    deductions = health.get("score_deductions") or []
    failures: list[dict] = []
    total = sum(int(v or 0) for v in categories.values())
    ev = _ev(name, args, "score", health.get("score"), total, None, "somma di category_scores")
    if health.get("score") != total:
        failures.append(ev)
    for cat, value in categories.items():
        if cat not in maxima:
            failures.append(_ev(name, args, f"category_max_scores.{cat}", None, None, None, "categoria senza massimo"))
            continue
        points = sum(int(d.get("points") or 0) for d in deductions if d.get("category") == cat)
        expected = max(0, int(maxima[cat]) - points)
        if value != expected:
            failures.append(_ev(name, args, f"category_scores.{cat}", value, expected, None,
                                f"massimo {maxima[cat]} − {points} punti di score_deductions"))
    for d in deductions:
        if d.get("category") not in categories:
            failures.append(_ev(name, args, f"score_deductions[code={d.get('code')}].category", d.get("category"),
                                None, None, "categoria sconosciuta"))
    return _judge(failures, "Il punteggio di salute non è spiegato dai punteggi di categoria e dalle penalità.", [ev])


# ---------------------------------------------------------------------------
# D-XRAY-SUMS
# ---------------------------------------------------------------------------


def check_xray_sums(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    _out, rows, p_name, p_args = _positions(ctx, scope)
    if not rows:
        return _empty_skip(p_name, p_args)
    xray, name, args = _read(ctx, "get_xray_summary", scope)
    failures: list[dict] = []
    passed: list[dict] = []
    for field in ("geographic_exposure", "sector_exposure"):
        buckets = xray.get(field) or {}
        if not buckets:
            continue
        k = len(buckets)
        total = sum(float(v or 0.0) for v in buckets.values())
        tol = max(0.05, 0.005 * k)
        ev = _ev(name, args, f"{field}[*]", _r(total), 100.0, tol, f"somma di {k} bucket")
        (failures if abs(total - 100.0) > tol + EPS else passed).append(ev)
    statuses = [_num(xray.get(k)) for k in ("available_pct", "not_applicable_pct", "missing_pct")]
    if all(v is not None for v in statuses):
        total = sum(statuses)
        ev = _ev(name, args, "available_pct + not_applicable_pct + missing_pct", _r(total), 100.0,
                 XRAY_STATUS_TOLERANCE)
        (failures if abs(total - 100.0) > XRAY_STATUS_TOLERANCE + EPS else passed).append(ev)
    return _judge(failures, "Le esposizioni dell'X-Ray non sommano a cento.", passed)


# ---------------------------------------------------------------------------
# D-XRAY-EMPTY (TASK-87)
# ---------------------------------------------------------------------------

# Messaggio con cui il server MCP maschera un'eccezione del tool (mcp_server/tools.py,
# _run_portfolio_tool): lo stesso di un guasto vero.
GENERIC_TOOL_ERROR_PREFIX = "Errore nell'esecuzione del tool"
# Copia di app.services.portfolio_doctor._xray.UNCLASSIFIED_LABEL (import non ammesso, §3.2).
XRAY_UNCLASSIFIED_LABEL = "Non classificato"


def _xray_empty_distribution(buckets: Any) -> bool:
    """Vuota, oppure il 100% in «Non classificato»."""
    if not buckets:
        return True
    if not isinstance(buckets, Mapping) or set(buckets) != {XRAY_UNCLASSIFIED_LABEL}:
        return False
    value = _num(buckets.get(XRAY_UNCLASSIFIED_LABEL))
    return value is not None and abs(value - 100.0) <= XRAY_STATUS_TOLERANCE + EPS


def check_xray_empty(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    _out, rows, p_name, p_args = _positions(ctx, scope)
    if rows:
        return _skip("not_applicable", "Il portafoglio ha posizioni: la regola riguarda il portafoglio vuoto.",
                     [_ev(p_name, p_args, "positions", len(rows), 0, None, "righe restituite")])
    p_ev = _ev(p_name, p_args, "positions", [], [], None, "nessuna riga")
    name, args = _scoped_args("get_xray_summary", scope)
    attempt = ctx.try_call(name, args)
    if not attempt["ok"]:
        message = str(attempt.get("error") or "")
        generic = message.startswith(GENERIC_TOOL_ERROR_PREFIX) or not message.strip()
        ev = _ev(name, args, "error", message[:200], None, None,
                 "errore generico, lo stesso di un guasto" if generic else "errore esplicito")
        if generic:
            return _fail("L'X-Ray del portafoglio vuoto risponde con l'errore generico del tool.", [p_ev, ev])
        return _pass([p_ev, ev])
    xray = attempt["result"] or {}
    failures: list[dict] = []
    passed: list[dict] = [p_ev]
    top = xray.get("top_underlying_holdings")
    ev = _ev(name, args, "top_underlying_holdings", top, [])
    (passed if not top else failures).append(ev)
    for field in ("geographic_exposure", "sector_exposure"):
        buckets = xray.get(field)
        ev = _ev(name, args, field, buckets, {}, XRAY_STATUS_TOLERANCE,
                 f"vuota o 100% «{XRAY_UNCLASSIFIED_LABEL}»")
        (passed if _xray_empty_distribution(buckets) else failures).append(ev)
    coverage = _num(xray.get("coverage_pct"))
    ev = _ev(name, args, "coverage_pct", xray.get("coverage_pct"), 0.0, None, "0 o null")
    (passed if coverage is None or abs(coverage) <= EPS else failures).append(ev)
    if failures:
        failures.insert(0, p_ev)
    return _judge(failures, "L'X-Ray del portafoglio vuoto riporta titoli, esposizioni o coperture.", passed)


# ---------------------------------------------------------------------------
# D-DUP-TRANSACTIONS
# ---------------------------------------------------------------------------


def _numbers_match(a: Any, b: Any) -> bool:
    """Stessa regola di ``csv_service._numbers_match``."""
    x = float(a or 0.0)
    y = float(b or 0.0)
    return abs(x - y) <= max(DUP_REL_TOLERANCE * max(abs(x), abs(y)), DUP_ABS_TOLERANCE)


def _same_row(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    return all(_numbers_match(a.get(k), b.get(k)) for k in ("quantity", "price", "fees"))


def check_dup_transactions(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    pid = scope["portfolio_id"]
    args = {"portfolio_id": pid}
    rows = ctx.transactions(pid)
    if not rows:
        return _skip("no_transactions", "Nessuna transazione da verificare.",
                     [_ev(TRANSACTIONS_TOOL, args, "[*]", 0, None, None, "numero di transazioni")])
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row.get("asset_id"), row.get("side"), row.get("trade_date"), row.get("trade_currency"))
        groups.setdefault(key, []).append(row)
    failures: list[dict] = []
    for (asset_id, side, day, ccy), members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        clusters: list[list[dict]] = []
        for row in members:
            for cluster in clusters:
                if _same_row(cluster[0], row):
                    cluster.append(row)
                    break
            else:
                clusters.append([row])
        threshold = 2 if side in CASH_SIDES else 3 if side in TRADE_SIDES else None
        if threshold is None:
            continue
        for cluster in clusters:
            if len(cluster) >= threshold:
                first = cluster[0]
                failures.append(_ev(
                    TRANSACTIONS_TOOL, args,
                    f"[side={side}][trade_date={day}][asset_id={asset_id}][trade_currency={ccy}]",
                    len(cluster), threshold - 1, None,
                    f"righe identiche (id {', '.join(str(r.get('id')) for r in cluster[:10])}; "
                    f"{first.get('symbol') or 'cassa'} quantità {first.get('quantity')} prezzo {first.get('price')} "
                    f"commissioni {first.get('fees')})",
                ))
    return _judge(failures, "Ci sono transazioni ripetute identiche: probabile import duplicato.",
                  [_ev(TRANSACTIONS_TOOL, args, "[*]", len(rows), None, None, "transazioni verificate")])


# ---------------------------------------------------------------------------
# D-TRADE-PRICE-SCALE
# ---------------------------------------------------------------------------


def check_trade_price_scale(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    pid = scope["portfolio_id"]
    args = {"portfolio_id": pid}
    rows = ctx.transactions(pid)
    if not rows:
        return _skip("no_transactions", "Nessuna transazione da verificare.",
                     [_ev(TRANSACTIONS_TOOL, args, "[*]", 0, None, None, "numero di transazioni")])
    _out, positions, _name, _pargs = _positions(ctx, scope)
    prices = {
        p.get("symbol"): float(p["market_price"])
        for p in positions
        if p.get("price_fallback") is None and _num(p.get("market_price")) and float(p["market_price"]) > 0
    }
    compared = 0
    failures: list[dict] = []
    for tx in rows:
        if tx.get("side") not in TRADE_SIDES or tx.get("symbol") not in prices:
            continue
        compared += 1
        market = prices[tx["symbol"]]
        price = float(tx.get("price") or 0.0)
        ratio = price / market
        if not (R_PX_MIN - EPS <= ratio <= R_PX_MAX + EPS):
            failures.append(_ev(
                TRANSACTIONS_TOOL, args, f"[id={tx.get('id')}].price", price, [R_PX_MIN * market, R_PX_MAX * market],
                None, f"{tx['symbol']} {tx.get('side')} del {tx.get('trade_date')} in {tx.get('trade_currency')}: "
                      f"rapporto {ratio:.4g} con il prezzo di mercato {market}",
            ))
            failures.append(_ev("get_positions", args, f"positions[symbol={tx['symbol']}].market_price", market))
    if not compared:
        return _skip("no_reference_data", "Nessuna operazione confrontabile con un prezzo di mercato.",
                     [_ev(TRANSACTIONS_TOOL, args, "[*]", len(rows), None, None, "transazioni lette")])
    return _judge(failures, "Il prezzo di alcune operazioni non è sulla scala del prezzo di mercato.",
                  [_ev(TRANSACTIONS_TOOL, args, "[side=buy|sell]", compared, None, None, "operazioni confrontate")])


# ---------------------------------------------------------------------------
# D-LSE-QUOTE-CURRENCY
# ---------------------------------------------------------------------------


def check_lse_quote_currency(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    symbol = str(scope["symbol"])
    args = {"portfolio_id": scope["portfolio_id"], "symbol": symbol}
    if not symbol.upper().endswith(".L"):
        return _skip("not_applicable", "Strumento non quotato a Londra.",
                     [_ev("search_asset_info", args, "symbol", symbol, None, None, "senza suffisso .L")])
    info = ctx.scoped("search_asset_info", scope, {"symbol": symbol})
    currency = info.get("currency")
    ev = _ev("search_asset_info", args, "currency", currency, sorted(LSE_CURRENCIES))
    if currency not in LSE_CURRENCIES:
        return _fail(f"Lo strumento quotato a Londra {symbol} ha valuta di quotazione {currency}.", [ev])
    return _pass([ev])


# ---------------------------------------------------------------------------
# D-FX-FLAGS-DECLARED
# ---------------------------------------------------------------------------


def check_fx_flags_declared(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    summary, s_name, s_args = _read(ctx, "get_portfolio_summary", scope)
    out, rows, p_name, p_args = _positions(ctx, scope)
    if not rows:
        return _empty_skip(p_name, p_args)
    truncated = _is_truncated(scope, out, rows)
    failures: list[dict] = []
    passed: list[dict] = []
    for flag, field in (("price_fallback", "price_fallback_symbols"), ("price_stale", "stale_price_symbols")):
        if flag == "price_fallback":
            from_rows = {r.get("symbol") for r in rows if r.get("price_fallback") == "avg_cost"}
        else:
            from_rows = {r.get("symbol") for r in rows if r.get("price_stale")}
        declared = set(summary.get(field) or [])
        ok = from_rows <= declared if truncated else from_rows == declared
        evs = [_ev(s_name, s_args, field, sorted(declared), sorted(from_rows), None,
                   "inclusione (righe troncate)" if truncated else None),
               _ev(p_name, p_args, f"positions[*].{flag}", sorted(from_rows))]
        if ok:
            passed.append(evs[0])
        else:
            failures.extend(evs)
    fx_rows = sorted(str(r.get("symbol")) for r in rows if r.get("fx_missing"))
    fx_declared = list(summary.get("fx_missing_currencies") or [])
    if fx_rows and not fx_declared:
        failures.extend([_ev(s_name, s_args, "fx_missing_currencies", fx_declared, "non vuoto"),
                         _ev(p_name, p_args, "positions[*].fx_missing", fx_rows)])
    lists = [summary.get(k) for k in ("fx_missing_currencies", "price_fallback_symbols", "stale_price_symbols")]
    if any(lists) and not str(summary.get("data_quality_note") or "").strip():
        failures.append(_ev(s_name, s_args, "data_quality_note", summary.get("data_quality_note"), "presente"))
    return _judge(failures, "Prezzi fermi, ripiegati o cambi mancanti non sono segnalati nel riepilogo.", passed)


# ---------------------------------------------------------------------------
# D-HELD-SYMBOL-MATCH
# ---------------------------------------------------------------------------


def check_held_symbol_match(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    symbol = str(scope["symbol"])
    args = {"portfolio_id": scope["portfolio_id"], "symbol": symbol}
    info = ctx.scoped("search_asset_info", scope, {"symbol": symbol})
    failures: list[dict] = []
    if info.get("match") != "portfolio":
        failures.append(_ev("search_asset_info", args, "match", info.get("match"), "portfolio"))
    if info.get("warning"):
        failures.append(_ev("search_asset_info", args, "warning", info.get("warning"), None))
    if str(info.get("symbol") or "").upper() != symbol.upper():
        failures.append(_ev("search_asset_info", args, "symbol", info.get("symbol"), symbol))
    return _judge(failures, f"La scheda di {symbol} si riferisce a un altro listing.",
                  [_ev("search_asset_info", args, "match", info.get("match"), "portfolio")])


# ---------------------------------------------------------------------------
# Dichiarazioni (rules.md §5, copiate esattamente)
# ---------------------------------------------------------------------------

_PA = ("portfolio", "aggregate")

RULES: list[dict[str, Any]] = [
    {
        "id": "D-WEIGHTS-SUM", "group": "D", "title": "I pesi delle posizioni sommano a cento",
        "area": "values", "severity": "P1", "findings": [], "scopes": list(_PA),
        "tools": ["get_positions", "get_aggregate_positions"], "check": check_weights_sum,
    },
    {
        "id": "D-SUMMARY-POSITIONS", "group": "D",
        "title": "Il riepilogo del portafoglio coincide con la somma delle posizioni",
        "area": "values", "severity": "P1", "findings": [], "scopes": list(_PA),
        "tools": ["get_portfolio_summary", "get_positions", "get_aggregate_summary", "get_aggregate_positions"],
        "check": check_summary_positions,
    },
    {
        "id": "D-POSITION-VALUE-PRICE", "group": "D",
        "title": "Il valore di ogni posizione è uguale a quantità per prezzo",
        "area": "values", "severity": "P2", "findings": ["V365-008"], "scopes": list(_PA),
        "tools": ["get_positions", "get_aggregate_positions"], "check": check_position_value_price,
    },
    {
        "id": "D-CASH-CONSISTENCY", "group": "D",
        "title": "La liquidità è la stessa nel riepilogo e nel saldo di cassa, e la sua scomposizione torna",
        "area": "values", "severity": "P1", "findings": ["C2-CASH-FX"], "scopes": ["portfolio"],
        "tools": ["get_portfolio_summary", "get_cash_balance"], "check": check_cash_consistency,
    },
    {
        "id": "D-SUMMARY-PERFORMANCE-VALUE", "group": "D",
        "title": "Il valore totale del riepilogo coincide con l'ultimo valore usato per i rendimenti",
        "area": "performance", "severity": "P1", "findings": ["C1-TWR-MIXED", "TASK-49"], "scopes": list(_PA),
        "tools": ["get_portfolio_summary", "get_positions", "get_aggregate_summary", "get_aggregate_positions",
                  TRANSACTIONS_TOOL, PERFORMANCE_AUDIT_TOOL],
        "check": check_summary_performance_value,
    },
    {
        "id": "D-AGG-SUMS", "group": "D",
        "title": "La vista aggregata somma esattamente i portafogli che la compongono",
        "area": "aggregate", "severity": "P1", "findings": ["V365-011"], "scopes": ["aggregate"],
        "tools": ["get_aggregate_summary", "get_portfolio_summary"], "check": check_agg_sums,
    },
    {
        "id": "D-AGG-POSITIONS", "group": "D",
        "title": "Le posizioni della vista aggregata uniscono quelle dei singoli portafogli",
        "area": "aggregate", "severity": "P1", "findings": ["V365-011"], "scopes": ["aggregate"],
        "tools": ["get_aggregate_positions", "get_positions"], "check": check_agg_positions,
    },
    {
        "id": "D-AGG-PERFORMANCE-VALUE", "group": "D",
        "title": "Il valore finale della performance aggregata è la somma dei valori dei portafogli",
        "area": "aggregate", "severity": "P2", "findings": ["V365-011"], "scopes": ["aggregate"],
        "tools": [TRANSACTIONS_TOOL, PERFORMANCE_AUDIT_TOOL], "check": check_agg_performance_value,
    },
    {
        "id": "D-PERF-RECOMPUTE", "group": "D",
        "title": "I rendimenti TWR e MWR coincidono con un ricalcolo indipendente",
        "area": "performance", "severity": "P1", "findings": ["C1-TWR-MIXED"], "scopes": list(_PA),
        "tools": [TRANSACTIONS_TOOL, PERFORMANCE_AUDIT_TOOL], "check": check_perf_recompute,
        "timeout_s": 60.0,
    },
    {
        "id": "D-PERF-TOOL-MATCH", "group": "D", "title": "Il rendimento mostrato è quello calcolato dal servizio",
        "area": "performance", "severity": "P2", "findings": ["C1-TWR-MIXED"], "scopes": list(_PA),
        "tools": ["get_performance", "get_aggregate_performance", TRANSACTIONS_TOOL, PERFORMANCE_AUDIT_TOOL],
        "check": check_perf_tool_match,
    },
    {
        "id": "D-DOCTOR-TER", "group": "D",
        "title": "Il TER medio è lo stesso nel Doctor, nella salute e nell'analisi dei costi",
        "area": "doctor", "severity": "P1", "findings": ["V365-007"], "scopes": ["portfolio"],
        "tools": ["read_doctor_metrics", "get_portfolio_health", "get_cost_breakdown", "get_positions",
                  "search_asset_info"],
        "check": check_doctor_ter,
    },
    {
        "id": "D-DOCTOR-CLASS-WEIGHTS", "group": "D",
        "title": "Le quote azionaria, obbligazionaria e oro del Doctor coincidono con lo stress test",
        "area": "doctor", "severity": "P1", "findings": ["V365-002"], "scopes": ["portfolio"],
        "tools": ["read_doctor_metrics", "get_stress_test", "get_positions"], "check": check_doctor_class_weights,
    },
    {
        "id": "D-DOCTOR-CONCENTRATION", "group": "D",
        "title": "Il peso della posizione più grande è lo stesso nel Doctor e nella salute",
        "area": "doctor", "severity": "P2", "findings": ["V365-010"], "scopes": ["portfolio"],
        "tools": ["read_doctor_metrics", "get_portfolio_health"], "check": check_doctor_concentration,
    },
    {
        "id": "D-DOCTOR-CASH", "group": "D",
        "title": "La liquidità del Doctor è la stessa del riepilogo",
        "area": "doctor", "severity": "P1", "findings": ["S-2026-11-11-01"], "scopes": list(_PA),
        "tools": ["build_doctor_scenario", "get_portfolio_summary", "get_aggregate_summary", "get_cash_balance",
                  "get_positions", "search_asset_info"],
        "check": check_doctor_cash,
    },
    {
        "id": "D-HEALTH-SCORE-BREAKDOWN", "group": "D",
        "title": "Il punteggio di salute è la somma dei punteggi di categoria e delle penalità dichiarate",
        "area": "doctor", "severity": "P2", "findings": ["V365-010"], "scopes": list(_PA),
        "tools": ["get_portfolio_health", "get_aggregate_health", "get_positions", "get_aggregate_positions"],
        "check": check_health_score_breakdown,
    },
    {
        "id": "D-XRAY-SUMS", "group": "D", "title": "Le esposizioni geografiche e settoriali sommano a cento",
        "area": "values", "severity": "P2", "findings": ["C6"], "scopes": list(_PA),
        "tools": ["get_xray_summary", "get_aggregate_xray", "get_positions", "get_aggregate_positions"],
        "check": check_xray_sums,
    },
    {
        "id": "D-XRAY-EMPTY", "group": "D", "title": "L'analisi X-Ray di un portafoglio vuoto risponde senza errori",
        "area": "classification", "severity": "P2", "findings": ["S-2026-11-11-04"], "scopes": ["portfolio"],
        "tools": ["get_positions", "get_xray_summary"], "check": check_xray_empty,
    },
    {
        "id": "D-DUP-TRANSACTIONS", "group": "D", "title": "Non ci sono transazioni importate due volte",
        "area": "data", "severity": "P1", "findings": ["V365-009", "V-DUP-IMPORT"], "scopes": ["portfolio"],
        "tools": [TRANSACTIONS_TOOL], "check": check_dup_transactions,
    },
    {
        "id": "D-TRADE-PRICE-SCALE", "group": "D",
        "title": "I prezzi delle operazioni importate sono sulla stessa scala del prezzo di mercato",
        "area": "data", "severity": "P1", "findings": ["V-XLSX-1000", "V365-008", "V-QUOTE-CCY-L"],
        "scopes": ["portfolio"], "tools": [TRANSACTIONS_TOOL, "get_positions"], "check": check_trade_price_scale,
    },
    {
        "id": "D-LSE-QUOTE-CURRENCY", "group": "D",
        "title": "Gli strumenti quotati a Londra hanno una valuta di quotazione plausibile",
        "area": "data", "severity": "P1", "findings": ["V-QUOTE-CCY-L", "V365-008"], "scopes": ["instrument"],
        "tools": ["search_asset_info"], "check": check_lse_quote_currency,
    },
    {
        "id": "D-FX-FLAGS-DECLARED", "group": "D",
        "title": "Prezzi fermi, prezzi mancanti e cambi mancanti sono segnalati nel riepilogo",
        "area": "values", "severity": "P2", "findings": ["C4-FX-FALLBACK"], "scopes": list(_PA),
        "tools": ["get_portfolio_summary", "get_positions", "get_aggregate_summary", "get_aggregate_positions"],
        "check": check_fx_flags_declared,
    },
    {
        "id": "D-HELD-SYMBOL-MATCH", "group": "D",
        "title": "La scheda di uno strumento in portafoglio si riferisce proprio a quel listing",
        "area": "data", "severity": "P2", "findings": ["V-LOOSE-SYMBOL"], "scopes": ["instrument"],
        "tools": ["search_asset_info"], "check": check_held_symbol_match,
    },
]
