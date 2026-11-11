"""Auditor dei calcoli — gruppo B: ribilanciamento, PAC e simulazioni (TASK-75).

Contratto: ``docs/auditor/architecture.md`` (dichiarazione ``RULES``, firma di
``check(ctx, scope)``, forma dell'esito e delle evidenze, argomenti canonici
§5.2) e ``docs/auditor/rules.md`` §3 (schede, tolleranze, casi di ``skip``).

Le regole sono funzioni pure sul contesto: leggono i dati solo con
``ctx.call`` / ``ctx.try_call`` sugli stessi tool che vedono Copilot, Tribunale
e Claude, con argomenti fissi (riproducibili e condivisi nella memo), e non
importano nulla dal motore dell'Auditor. Solo libreria standard.

Finding di origine: V365-003 (i proventi delle vendite non finanziavano gli
acquisti, ``cash_used`` contava due volte la liquidità) e proprietà di
conservazione delle simulazioni (PAC, what-if).
"""

from __future__ import annotations

import math
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Tolleranze (rules.md §0.2)
# ---------------------------------------------------------------------------

T_EUR = 0.01
T_PP = 0.005
T_PP2 = 0.02
EPS = 1e-9
MAX_EVIDENCE_ITEMS = 50
POSITIONS_ROW_LIMIT = 30  # get_positions restituisce al più 30 righe (rules.md §0.3)


def t_sum_eur(n: int) -> float:
    """Somma di n importi arrotondati a 2 decimali: 0,005 × n + 0,01 €."""
    return 0.005 * n + 0.01


# ---------------------------------------------------------------------------
# Argomenti canonici (architecture.md §5.2, rules.md §3)
# ---------------------------------------------------------------------------

REBALANCE_TOOL = "calculate_rebalance_orders"
PAC_TOOL = "calculate_pac_contribution"
WHAT_IF_TOOL = "calculate_what_if"
POSITIONS_TOOL = "get_positions"
SUMMARY_TOOL = "get_portfolio_summary"
TARGET_DRIFT_TOOL = "get_target_drift"

REBALANCE_ARGS: dict[str, dict[str, Any]] = {
    "rebalance": {"mode": "rebalance"},                              # R
    "buy_only": {"mode": "buy_only", "available_cash": 1000.0},      # BO
    "sell_only": {"mode": "sell_only"},                              # SO
}
BUY_ONLY_EXTRA_CASH = 1000.0
PAC_MONTHLY_AMOUNT = 500.0
PAC_ARGS: dict[str, Any] = {"monthly_amount": PAC_MONTHLY_AMOUNT}
WHAT_IF_BUY_AMOUNT = 1000.0
WHAT_IF_SELL_EXCESS = 1000.0
WHAT_IF_MIN_POSITION_VALUE = 0.02


# ---------------------------------------------------------------------------
# Esiti ed evidenze (architecture.md §3.3)
# ---------------------------------------------------------------------------


def _ev(
    tool: str, args: Mapping[str, Any], path: str, observed: Any,
    expected: Any = None, tolerance: float | None = None, note: str | None = None,
) -> dict[str, Any]:
    return {
        "tool": tool,
        "args": dict(args),
        "path": path,
        "observed": observed,
        "expected": expected,
        "tolerance": None if tolerance is None else round(float(tolerance), 9),
        "note": note,
    }


def _pass(evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": "pass", "reason_code": None, "reason": None,
            "evidence": list(evidence or [])[:MAX_EVIDENCE_ITEMS]}


def _fail(reason: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "fail", "reason_code": "invariant_violated", "reason": reason,
            "evidence": list(evidence)[:MAX_EVIDENCE_ITEMS]}


def _skip(code: str, reason: str, evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"status": "skip", "reason_code": code, "reason": reason,
            "evidence": list(evidence or [])[:MAX_EVIDENCE_ITEMS]}


def _num(value: Any) -> float | None:
    """Numero finito o None (``sanitize_output`` trasforma i non finiti in null)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _r(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


# ---------------------------------------------------------------------------
# Letture comuni
# ---------------------------------------------------------------------------


def _pid_args(scope: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    # Equivale a scoped_tool_args per uno scope portfolio: stessa chiave di memo.
    return {"portfolio_id": int(scope["portfolio_id"]), **dict(extra or {})}


def _positions(ctx: Any, scope: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    args = _pid_args(scope)
    result = ctx.call(POSITIONS_TOOL, args)
    return args, list(result.get("positions") or [])


def _empty_skip(args: Mapping[str, Any]) -> dict[str, Any]:
    return _skip(
        "empty_portfolio", "Il portafoglio non ha posizioni.",
        [_ev(POSITIONS_TOOL, args, "positions", [], note="nessuna posizione")],
    )


def _load_rebalance(
    ctx: Any, scope: Mapping[str, Any], modes: tuple[str, ...],
) -> tuple[list[tuple[str, dict[str, Any], dict[str, Any]]] | None, dict[str, Any] | None]:
    """Esegue il ribilanciamento nelle modalità indicate.

    Restituisce ``(runs, None)`` oppure ``(None, outcome)`` quando la regola
    non può giudicare (portafoglio vuoto, nessun target) o i totali mancano
    solo in alcune modalità (incoerenza: ``fail``).
    """
    pos_args, positions = _positions(ctx, scope)
    if not positions:
        return None, _empty_skip(pos_args)
    runs = []
    for mode in modes:
        args = _pid_args(scope, REBALANCE_ARGS[mode])
        runs.append((mode, args, ctx.call(REBALANCE_TOOL, args)))
    missing = [(mode, args) for mode, args, res in runs if not isinstance(res.get("totals"), dict)]
    if missing and len(missing) == len(runs):
        mode, args = missing[0]
        return None, _skip(
            "no_targets", "Il portafoglio non ha pesi obiettivo configurati.",
            [_ev(REBALANCE_TOOL, args, "totals", None, note="totals assente: nessun target")],
        )
    if missing:
        return None, _fail(
            "Il ribilanciamento restituisce i totali solo in alcune modalità.",
            [_ev(REBALANCE_TOOL, args, "totals", None, expected="oggetto totals",
                 note=f"totals assente in modalità {mode}") for mode, args in missing],
        )
    return runs, None


def _orders(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [o for o in (result.get("orders") or []) if isinstance(o, dict)]


def _order_path(index: int, order: Mapping[str, Any], field: str) -> str:
    return f"orders[{index}].{field}"


def _order_note(mode: str, order: Mapping[str, Any]) -> str:
    return f"modalità {mode}, {order.get('side')} {order.get('symbol')}"


# ---------------------------------------------------------------------------
# B-REB-CASH-CONSERVATION
# ---------------------------------------------------------------------------


def check_reb_cash_conservation(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    runs, early = _load_rebalance(ctx, scope, ("rebalance", "buy_only", "sell_only"))
    if early is not None:
        return early
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for mode, args, res in runs:
        totals = res["totals"]
        orders = _orders(res)
        n = len(orders)
        cash_before = _num(totals.get("cash_before"))
        extra = _num(totals.get("extra_cash"))
        sells = _num(totals.get("sells_eur"))
        buys = _num(totals.get("buys_eur"))
        cash_after = _num(totals.get("cash_after"))
        fields = {"cash_before": cash_before, "extra_cash": extra, "sells_eur": sells,
                  "buys_eur": buys, "cash_after": cash_after}
        bad = [k for k, v in fields.items() if v is None]
        if bad:
            violations += [_ev(REBALANCE_TOOL, args, f"totals.{k}", totals.get(k), expected="numero",
                               note=f"modalità {mode}: valore mancante") for k in bad]
            continue
        expected_after = cash_before + extra + sells - buys
        ev = _ev(REBALANCE_TOOL, args, "totals.cash_after", cash_after, _r(expected_after, 2), T_EUR,
                 f"modalità {mode}: cash_before + extra_cash + sells_eur − buys_eur")
        (violations if abs(cash_after - expected_after) > T_EUR + EPS else passed).append(ev)

        for side, total, label in (("sell", sells, "sells_eur"), ("buy", buys, "buys_eur")):
            amounts = [_num(o.get("amount_eur")) for o in orders if o.get("side") == side]
            if any(a is None for a in amounts):
                violations.append(_ev(REBALANCE_TOOL, args, "orders[*].amount_eur", None, expected="numero",
                                      note=f"modalità {mode}: importo di un ordine {side} mancante"))
                continue
            total_orders = sum(amounts)
            tol = t_sum_eur(n)
            ev = _ev(REBALANCE_TOOL, args, f"totals.{label}", total, _r(total_orders, 2), tol,
                     f"modalità {mode}: somma degli amount_eur degli ordini {side}")
            (violations if abs(total - total_orders) > tol + EPS else passed).append(ev)

        if totals.get("invariant_ok") is not True:
            violations.append(_ev(REBALANCE_TOOL, args, "totals.invariant_ok", totals.get("invariant_ok"),
                                  True, None, f"modalità {mode}"))
        if mode == "buy_only" and extra != BUY_ONLY_EXTRA_CASH:
            violations.append(_ev(REBALANCE_TOOL, args, "totals.extra_cash", extra, BUY_ONLY_EXTRA_CASH,
                                  None, "modalità buy_only: available_cash passato al tool"))
    if violations:
        return _fail(
            "Nel ribilanciamento la liquidità finale non torna con liquidità iniziale, "
            "nuova liquidità, vendite e acquisti.", violations,
        )
    return _pass(passed)


# ---------------------------------------------------------------------------
# B-REB-CASH-NONNEG
# ---------------------------------------------------------------------------


def check_reb_cash_nonneg(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    runs, early = _load_rebalance(ctx, scope, ("rebalance", "buy_only", "sell_only"))
    if early is not None:
        return early
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for mode, args, res in runs:
        totals = res["totals"]
        n = len(_orders(res))
        cash_before = _num(totals.get("cash_before"))
        extra = _num(totals.get("extra_cash"))
        sells = _num(totals.get("sells_eur"))
        buys = _num(totals.get("buys_eur"))
        cash_after = _num(totals.get("cash_after"))
        if cash_after is None:
            violations.append(_ev(REBALANCE_TOOL, args, "totals.cash_after", totals.get("cash_after"),
                                  expected="numero ≥ 0", note=f"modalità {mode}: valore mancante"))
        else:
            ev = _ev(REBALANCE_TOOL, args, "totals.cash_after", cash_after, 0.0, T_EUR,
                     f"modalità {mode}: liquidità residua ≥ 0")
            (violations if cash_after < -T_EUR - EPS else passed).append(ev)
        if None in (cash_before, extra, sells, buys):
            violations.append(_ev(REBALANCE_TOOL, args, "totals", totals, expected="importi numerici",
                                  note=f"modalità {mode}: totali mancanti"))
            continue
        available = cash_before + extra + sells
        tol = t_sum_eur(n)
        ev = _ev(REBALANCE_TOOL, args, "totals.buys_eur", buys, _r(available, 2), tol,
                 f"modalità {mode}: acquisti ≤ cash_before + extra_cash + sells_eur")
        (violations if buys > available + tol + EPS else passed).append(ev)
    if violations:
        return _fail(
            "Il ribilanciamento spende più della liquidità disponibile più i proventi delle vendite.",
            violations,
        )
    return _pass(passed)


# ---------------------------------------------------------------------------
# B-REB-SELLS-REACH-TARGET
# ---------------------------------------------------------------------------


def check_reb_sells_reach_target(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    runs, early = _load_rebalance(ctx, scope, ("rebalance", "sell_only"))
    if early is not None:
        return early
    if not any(_orders(res) for _, _, res in runs):
        return _skip(
            "not_applicable", "Il portafoglio è già entro la banda di tolleranza: nessun ordine.",
            [_ev(REBALANCE_TOOL, args, "orders", [], note=f"modalità {mode}") for mode, args, _ in runs],
        )
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for mode, args, res in runs:
        orders = _orders(res)
        n = len(orders)
        reduced: list[dict[str, Any]] = []
        for i, o in enumerate(orders):
            wa = _num(o.get("weight_after_pct"))
            tw = _num(o.get("target_weight_pct"))
            side = o.get("side")
            if side not in ("buy", "sell"):
                continue
            if side == "buy" and mode != "rebalance":
                continue
            if wa is None or tw is None:
                violations.append(_ev(REBALANCE_TOOL, args, _order_path(i, o, "weight_after_pct"),
                                      o.get("weight_after_pct"), o.get("target_weight_pct"), None,
                                      _order_note(mode, o) + ": peso mancante"))
                continue
            if side == "sell":
                ev = _ev(REBALANCE_TOOL, args, _order_path(i, o, "weight_after_pct"), wa, tw, T_PP2,
                         _order_note(mode, o) + ": dopo la vendita il peso è il target")
                (violations if abs(wa - tw) > T_PP2 + EPS else passed).append(ev)
            else:
                ev = _ev(REBALANCE_TOOL, args, _order_path(i, o, "weight_after_pct"), wa, tw, T_PP2,
                         _order_note(mode, o) + ": l'acquisto non supera il target")
                (violations if wa > tw + T_PP2 + EPS else passed).append(ev)
                if wa < tw - T_PP2 - EPS:
                    reduced.append(o)
        if reduced:
            totals = res.get("totals") or {}
            cash_after = _num(totals.get("cash_after"))
            tol = t_sum_eur(n)
            ev = _ev(REBALANCE_TOOL, args, "totals.cash_after", totals.get("cash_after"), 0.0, tol,
                     f"modalità {mode}: acquisti ridotti ({', '.join(str(o.get('symbol')) for o in reduced)}) "
                     "con liquidità residua")
            (violations if cash_after is None or cash_after > tol + EPS else passed).append(ev)
    if violations:
        return _fail(
            "Le vendite (o gli acquisti) del ribilanciamento non portano gli strumenti al peso obiettivo.",
            violations,
        )
    return _pass(passed)


# ---------------------------------------------------------------------------
# B-REB-DRIFT-NONINCREASING
# ---------------------------------------------------------------------------


def check_reb_drift_nonincreasing(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    runs, early = _load_rebalance(ctx, scope, ("rebalance", "buy_only", "sell_only"))
    if early is not None:
        return early
    if not any(_orders(res) for _, _, res in runs):
        return _skip(
            "not_applicable", "Il portafoglio è già entro la banda di tolleranza: nessun ordine.",
            [_ev(REBALANCE_TOOL, args, "orders", [], note=f"modalità {mode}") for mode, args, _ in runs],
        )
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for mode, args, res in runs:
        for i, o in enumerate(_orders(res)):
            wa = _num(o.get("weight_after_pct"))
            cw = _num(o.get("current_weight_pct"))
            tw = _num(o.get("target_weight_pct"))
            if None in (wa, cw, tw):
                violations.append(_ev(REBALANCE_TOOL, args, f"orders[{i}]", o, expected="pesi numerici",
                                      note=_order_note(mode, o) + ": peso mancante"))
                continue
            before = abs(cw - tw)
            after = abs(wa - tw)
            ev = _ev(REBALANCE_TOOL, args, _order_path(i, o, "weight_after_pct"), wa, tw, T_PP2,
                     _order_note(mode, o) + f": scostamento {round(before, 4)} → {round(after, 4)} pp")
            (violations if after > before + T_PP2 + EPS else passed).append(ev)
    if violations:
        return _fail("Dopo gli ordini lo scostamento di uno strumento dal peso obiettivo aumenta.", violations)
    return _pass(passed)


# ---------------------------------------------------------------------------
# B-REB-MODE-SIDES
# ---------------------------------------------------------------------------


def check_reb_mode_sides(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    runs, early = _load_rebalance(ctx, scope, ("buy_only", "sell_only"))
    if early is not None:
        return early
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for mode, args, res in runs:
        forbidden, total_key = ("sell", "sells_eur") if mode == "buy_only" else ("buy", "buys_eur")
        for i, o in enumerate(_orders(res)):
            if o.get("side") == forbidden:
                violations.append(_ev(REBALANCE_TOOL, args, _order_path(i, o, "side"), forbidden, None, None,
                                      _order_note(mode, o) + f": ordine {forbidden} non ammesso"))
        total = res["totals"].get(total_key)
        ev = _ev(REBALANCE_TOOL, args, f"totals.{total_key}", total, 0.0, None, f"modalità {mode}")
        (violations if _num(total) != 0.0 else passed).append(ev)
    if violations:
        return _fail(
            "La modalità del ribilanciamento non è rispettata: compaiono vendite con sola nuova "
            "liquidità o acquisti con sole vendite.", violations,
        )
    return _pass(passed)


# ---------------------------------------------------------------------------
# B-REB-SELL-CAP
# ---------------------------------------------------------------------------


def check_reb_sell_cap(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    runs, early = _load_rebalance(ctx, scope, ("rebalance", "sell_only"))
    if early is not None:
        return early
    pos_args, positions = _positions(ctx, scope)
    truncated = len(positions) >= POSITIONS_ROW_LIMIT
    by_symbol = {p.get("symbol"): p for p in positions}
    sells = [(mode, args, i, o) for mode, args, res in runs
             for i, o in enumerate(_orders(res)) if o.get("side") == "sell"]
    if not sells:
        return _skip(
            "not_applicable", "Il ribilanciamento non propone vendite.",
            [_ev(REBALANCE_TOOL, args, "orders[side=sell]", [], note=f"modalità {mode}")
             for mode, args, _ in runs],
        )
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    unverifiable: list[dict[str, Any]] = []
    for mode, args, i, o in sells:
        symbol = o.get("symbol")
        amount = _num(o.get("amount_eur"))
        row = by_symbol.get(symbol)
        if row is None:
            ev = _ev(POSITIONS_TOOL, pos_args, f"positions[symbol={symbol}]", None, "riga della posizione",
                     None, _order_note(mode, o) + ": strumento venduto assente dalle posizioni")
            (unverifiable if truncated else violations).append(ev)
            continue
        mv = _num(row.get("market_value"))
        if amount is None or mv is None:
            violations.append(_ev(REBALANCE_TOOL, args, _order_path(i, o, "amount_eur"), o.get("amount_eur"),
                                  row.get("market_value"), T_EUR, _order_note(mode, o) + ": importo mancante"))
            continue
        ok = amount <= mv + T_EUR + EPS
        ev_order = _ev(REBALANCE_TOOL, args, _order_path(i, o, "amount_eur"), amount, mv, T_EUR,
                       _order_note(mode, o) + ": vendita ≤ valore della posizione")
        if ok:
            passed.append(ev_order)
        else:
            violations += [ev_order, _ev(POSITIONS_TOOL, pos_args, f"positions[symbol={symbol}].market_value",
                                         mv, None, None, "valore della posizione")]
    if violations:
        return _fail("Il ribilanciamento vende più di quanto si possiede.", violations)
    if unverifiable:
        return _skip(
            "truncated_output",
            "Le posizioni sono limitate a 30 righe: non tutte le vendite sono verificabili.",
            unverifiable,
        )
    return _pass(passed)


# ---------------------------------------------------------------------------
# PAC
# ---------------------------------------------------------------------------


def _load_pac(ctx: Any, scope: Mapping[str, Any]):
    pos_args, positions = _positions(ctx, scope)
    if not positions:
        return None, None, _empty_skip(pos_args)
    args = _pid_args(scope, PAC_ARGS)
    result = ctx.call(PAC_TOOL, args)
    if "total_allocated" not in result:
        return None, None, _skip(
            "no_targets", "Il portafoglio non ha pesi obiettivo configurati.",
            [_ev(PAC_TOOL, args, "total_allocated", None, note="total_allocated assente: nessun target")],
        )
    return args, result, None


def check_pac_sum(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    args, pac, early = _load_pac(ctx, scope)
    if early is not None:
        return early
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    monthly = _num(pac.get("monthly_amount"))
    ev = _ev(PAC_TOOL, args, "monthly_amount", pac.get("monthly_amount"), PAC_MONTHLY_AMOUNT, None,
             "importo indicato al tool")
    (passed if monthly == PAC_MONTHLY_AMOUNT else violations).append(ev)

    total = _num(pac.get("total_allocated"))
    ev = _ev(PAC_TOOL, args, "total_allocated", pac.get("total_allocated"), PAC_MONTHLY_AMOUNT, T_EUR,
             "totale allocato = importo indicato")
    (violations if total is None or abs(total - PAC_MONTHLY_AMOUNT) > T_EUR + EPS else passed).append(ev)

    rows = [d for d in (pac.get("distribution") or []) if isinstance(d, dict)]
    amounts = [_num(d.get("amount_eur")) for d in rows]
    n = len(rows)
    if any(a is None for a in amounts):
        violations.append(_ev(PAC_TOOL, args, "distribution[*].amount_eur", None, "numero", None,
                              "importo di una riga mancante"))
    elif total is not None:
        dist_sum = sum(amounts)
        tol = t_sum_eur(n)
        ev = _ev(PAC_TOOL, args, "distribution[*].amount_eur", _r(dist_sum, 2), total, tol,
                 f"somma su {n} righe = total_allocated")
        (violations if abs(dist_sum - total) > tol + EPS else passed).append(ev)
    if violations:
        return _fail(
            "Nel PAC la somma dei versamenti per strumento non è uguale all'importo indicato.", violations,
        )
    return _pass(passed)


def check_pac_underweight_only(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    args, pac, early = _load_pac(ctx, scope)
    if early is not None:
        return early
    rows = [d for d in (pac.get("distribution") or []) if isinstance(d, dict)]
    if not rows:
        return _skip(
            "not_applicable", "Il PAC non distribuisce l'importo su alcuno strumento.",
            [_ev(PAC_TOOL, args, "distribution", [], note="distribuzione vuota")],
        )
    drift_args = _pid_args(scope)
    drift = ctx.call(TARGET_DRIFT_TOOL, drift_args)
    drift_symbols = {d.get("symbol") for d in (drift.get("drift") or []) if isinstance(d, dict)}
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for i, d in enumerate(rows):
        symbol = d.get("symbol")
        amount = _num(d.get("amount_eur"))
        cw = _num(d.get("current_weight"))
        tw = _num(d.get("target_weight"))
        ev = _ev(PAC_TOOL, args, f"distribution[{i}].amount_eur", d.get("amount_eur"), 0.0, None,
                 f"{symbol}: versamento ≥ 0")
        (violations if amount is None or amount < -EPS else passed).append(ev)
        ev = _ev(PAC_TOOL, args, f"distribution[{i}].current_weight", d.get("current_weight"),
                 d.get("target_weight"), T_PP2, f"{symbol}: peso attuale ≤ peso obiettivo")
        (violations if cw is None or tw is None or cw > tw + T_PP2 + EPS else passed).append(ev)
        if symbol not in drift_symbols:
            violations.append(_ev(TARGET_DRIFT_TOOL, drift_args, f"drift[symbol={symbol}]", None,
                                  symbol, None, "strumento del PAC assente dai target"))
    if violations:
        return _fail("Il PAC versa su uno strumento che non è sotto il peso obiettivo.", violations)
    return _pass(passed)


# ---------------------------------------------------------------------------
# What-if
# ---------------------------------------------------------------------------


def _load_what_if_base(ctx: Any, scope: Mapping[str, Any]):
    pos_args, positions = _positions(ctx, scope)
    if not positions:
        return None, _empty_skip(pos_args)
    first = positions[0]
    sum_args = _pid_args(scope)
    summary = ctx.call(SUMMARY_TOOL, sum_args)
    return {
        "pos_args": pos_args, "sum_args": sum_args, "row": first, "symbol": first.get("symbol"),
        "w": _num(first.get("weight")), "v": _num(first.get("market_value")),
        "mv": _num(summary.get("market_value")), "mv_raw": summary.get("market_value"),
    }, None


def _base_violations(base: Mapping[str, Any], need_v: bool) -> list[dict[str, Any]]:
    out = []
    if base["w"] is None:
        out.append(_ev(POSITIONS_TOOL, base["pos_args"], "positions[0].weight", base["row"].get("weight"),
                       "numero", None, "peso della prima posizione mancante"))
    if need_v and base["v"] is None:
        out.append(_ev(POSITIONS_TOOL, base["pos_args"], "positions[0].market_value",
                       base["row"].get("market_value"), "numero", None, "valore della prima posizione mancante"))
    if base["mv"] is None:
        out.append(_ev(SUMMARY_TOOL, base["sum_args"], "market_value", base["mv_raw"], "numero", None,
                       "valore del portafoglio mancante"))
    return out


def check_whatif_buy_weight(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    base, early = _load_what_if_base(ctx, scope)
    if early is not None:
        return early
    bad = _base_violations(base, need_v=False)
    if bad:
        return _fail("I dati di partenza della simulazione di acquisto non sono numerici.", bad)
    symbol, w, mv = base["symbol"], base["w"], base["mv"]
    args = _pid_args(scope, {"action": "buy", "symbol": symbol, "amount_eur": WHAT_IF_BUY_AMOUNT})
    res = ctx.call(WHAT_IF_TOOL, args)
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    old_w = _num(res.get("old_weight"))
    ev = _ev(WHAT_IF_TOOL, args, "old_weight", res.get("old_weight"), w, T_PP,
             f"peso attuale di {symbol} come in get_positions")
    (violations if old_w is None or abs(old_w - w) > T_PP + EPS else passed).append(ev)

    expected_new = (w * mv / 100.0 + WHAT_IF_BUY_AMOUNT) / (mv + WHAT_IF_BUY_AMOUNT) * 100.0
    new_w = _num(res.get("new_weight"))
    ev = _ev(WHAT_IF_TOOL, args, "new_weight", res.get("new_weight"), _r(expected_new, 4), T_PP2,
             f"(w × MV / 100 + 1000) / (MV + 1000) × 100 con w = {w}, MV = {mv}")
    (violations if new_w is None or abs(new_w - expected_new) > T_PP2 + EPS else passed).append(ev)

    max_after = _num(res.get("max_position_weight_after"))
    if new_w is not None:
        ev = _ev(WHAT_IF_TOOL, args, "max_position_weight_after", res.get("max_position_weight_after"),
                 new_w, T_PP, "peso massimo dopo l'acquisto ≥ nuovo peso dello strumento")
        (violations if max_after is None or max_after < new_w - T_PP - EPS else passed).append(ev)
    if violations:
        violations.append(_ev(SUMMARY_TOOL, base["sum_args"], "market_value", mv, None, None,
                              "MV usato nel ricalcolo"))
        return _fail("La simulazione di un acquisto non ricalcola correttamente il peso.", violations)
    return _pass(passed)


def check_whatif_sell_bound(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    base, early = _load_what_if_base(ctx, scope)
    if early is not None:
        return early
    bad = _base_violations(base, need_v=True)
    if bad:
        return _fail("I dati di partenza della simulazione di vendita non sono numerici.", bad)
    symbol, w, mv, v = base["symbol"], base["w"], base["mv"], base["v"]
    if v < WHAT_IF_MIN_POSITION_VALUE:
        return _skip(
            "not_applicable", "La posizione principale vale meno di 0,02 €: nessuna vendita simulabile.",
            [_ev(POSITIONS_TOOL, base["pos_args"], "positions[0].market_value", v,
                 WHAT_IF_MIN_POSITION_VALUE, None, symbol)],
        )
    amount = round(v / 2.0, 2)
    args = _pid_args(scope, {"action": "sell", "symbol": symbol, "amount_eur": amount})
    res = ctx.call(WHAT_IF_TOOL, args)
    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    denominator = mv - amount
    new_w = _num(res.get("new_weight"))
    if denominator <= EPS:
        violations.append(_ev(SUMMARY_TOOL, base["sum_args"], "market_value", mv, f"> {amount}", None,
                              "valore del portafoglio non superiore alla vendita simulata"))
    else:
        expected_new = (w * mv / 100.0 - amount) / denominator * 100.0
        ev = _ev(WHAT_IF_TOOL, args, "new_weight", res.get("new_weight"), _r(expected_new, 4), T_PP2,
                 f"(w × MV / 100 − A) / (MV − A) × 100 con w = {w}, MV = {mv}, A = {amount}")
        (violations if new_w is None or abs(new_w - expected_new) > T_PP2 + EPS else passed).append(ev)

    over_amount = round(v + WHAT_IF_SELL_EXCESS, 2)
    over_args = _pid_args(scope, {"action": "sell", "symbol": symbol, "amount_eur": over_amount})
    over = ctx.try_call(WHAT_IF_TOOL, over_args)
    ev = _ev(WHAT_IF_TOOL, over_args, "ok", over.get("ok"), False, None,
             f"vendita di {over_amount} € oltre il valore della posizione ({v} €) rifiutata"
             + (f": {over.get('error')}" if over.get("error") else ""))
    if over.get("ok") is False:
        passed.append(ev)
    else:
        result = over.get("result") or {}
        violations.append(ev)
        if "new_weight" in result:
            violations.append(_ev(WHAT_IF_TOOL, over_args, "new_weight", result.get("new_weight"), None, None,
                                  "peso restituito per una vendita impossibile"))
    if violations:
        return _fail(
            "La simulazione di una vendita non ricalcola il peso o accetta una vendita oltre la posizione.",
            violations,
        )
    return _pass(passed)


# ---------------------------------------------------------------------------
# Dichiarazioni (rules.md §3: id, titoli, severità, finding, scope copiati)
# ---------------------------------------------------------------------------

_REB_TOOLS = ["calculate_rebalance_orders", "get_positions"]

RULES: list[dict[str, Any]] = [
    {
        "id": "B-REB-CASH-CONSERVATION",
        "group": "B",
        "title": "Il ribilanciamento conserva la liquidità: vendite e acquisti tornano al centesimo",
        "area": "rebalance",
        "severity": "P0",
        "findings": ["V365-003"],
        "scopes": ["portfolio"],
        "tools": list(_REB_TOOLS),
        "check": check_reb_cash_conservation,
    },
    {
        "id": "B-REB-CASH-NONNEG",
        "group": "B",
        "title": "Il ribilanciamento non spende più della liquidità disponibile",
        "area": "rebalance",
        "severity": "P0",
        "findings": ["V365-003"],
        "scopes": ["portfolio"],
        "tools": list(_REB_TOOLS),
        "check": check_reb_cash_nonneg,
    },
    {
        "id": "B-REB-SELLS-REACH-TARGET",
        "group": "B",
        "title": "Le vendite del ribilanciamento portano ogni strumento al suo peso obiettivo",
        "area": "rebalance",
        "severity": "P1",
        "findings": ["V365-003"],
        "scopes": ["portfolio"],
        "tools": list(_REB_TOOLS),
        "check": check_reb_sells_reach_target,
    },
    {
        "id": "B-REB-DRIFT-NONINCREASING",
        "group": "B",
        "title": "Dopo gli ordini lo scostamento dai pesi obiettivo non aumenta",
        "area": "rebalance",
        "severity": "P1",
        "findings": ["V365-003"],
        "scopes": ["portfolio"],
        "tools": list(_REB_TOOLS),
        "check": check_reb_drift_nonincreasing,
    },
    {
        "id": "B-REB-MODE-SIDES",
        "group": "B",
        "title": "Con sola nuova liquidità il ribilanciamento non propone vendite",
        "area": "rebalance",
        "severity": "P1",
        "findings": ["V365-003"],
        "scopes": ["portfolio"],
        "tools": list(_REB_TOOLS),
        "check": check_reb_mode_sides,
    },
    {
        "id": "B-REB-SELL-CAP",
        "group": "B",
        "title": "Non si vende mai più di quanto si possiede",
        "area": "rebalance",
        "severity": "P1",
        "findings": ["V365-003"],
        "scopes": ["portfolio"],
        "tools": list(_REB_TOOLS),
        "check": check_reb_sell_cap,
    },
    {
        "id": "B-PAC-SUM",
        "group": "B",
        "title": "Nel PAC la somma dei versamenti per strumento è uguale all'importo indicato",
        "area": "rebalance",
        "severity": "P1",
        "findings": [],
        "scopes": ["portfolio"],
        "tools": ["calculate_pac_contribution", "get_positions"],
        "check": check_pac_sum,
    },
    {
        "id": "B-PAC-UNDERWEIGHT-ONLY",
        "group": "B",
        "title": "Il PAC versa solo sugli strumenti sotto il peso obiettivo",
        "area": "rebalance",
        "severity": "P2",
        "findings": [],
        "scopes": ["portfolio"],
        "tools": ["calculate_pac_contribution", "get_target_drift", "get_positions"],
        "check": check_pac_underweight_only,
    },
    {
        "id": "B-WHATIF-BUY-WEIGHT",
        "group": "B",
        "title": "La simulazione di un acquisto ricalcola correttamente il peso",
        "area": "simulation",
        "severity": "P2",
        "findings": [],
        "scopes": ["portfolio"],
        "tools": ["get_positions", "get_portfolio_summary", "calculate_what_if"],
        "check": check_whatif_buy_weight,
    },
    {
        "id": "B-WHATIF-SELL-BOUND",
        "group": "B",
        "title": "La simulazione di una vendita ricalcola il peso e rifiuta vendite oltre la posizione",
        "area": "simulation",
        "severity": "P2",
        "findings": [],
        "scopes": ["portfolio"],
        "tools": ["get_positions", "get_portfolio_summary", "calculate_what_if"],
        "check": check_whatif_sell_bound,
    },
]
