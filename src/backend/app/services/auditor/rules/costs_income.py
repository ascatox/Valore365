"""Auditor — gruppo C: costi, reddito, dividendi, Monte Carlo e variazioni giornaliere (TASK-76).

Contratto: ``docs/auditor/architecture.md`` (dichiarazione ``RULES``, ``check(ctx, scope)``, esiti ed
evidenze) e ``docs/auditor/rules.md`` §4 (schede, tolleranze di §0.2, comportamenti di §0.3).

Le regole leggono i dati solo tramite il contesto (``ctx.scoped`` / ``ctx.call`` /
``ctx.transactions``) e confrontano l'output dei tool fra loro o con un ricalcolo indipendente.
Il modulo non importa nulla dal motore dell'Auditor né dall'app: solo la libreria standard.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Tolleranze (rules.md §0.2)
# ---------------------------------------------------------------------------

EPS = 1e-9
T_EUR = 0.01
T_PP = 0.005
T_MC = 0.03
R_TER_MIN = 0.01
R_TER_MAX = 3.00
WEIGHTED_TER_MAX = 3.00
INCOME_BUCKETS_TOL = 0.02
POSITIONS_ROW_LIMIT = 30
MAX_EVIDENCE = 50

MC_YEARS = list(range(1, 11))
INCOME_PROJECTION_YEARS = [1, 3, 5]
INCOME_BUCKET_FIELDS = {
    "equity": "equity_annual_dividends_eur",
    "fixed_income": "fixed_income_annual_dividends_eur",
    "other_or_unknown": "other_or_unknown_annual_dividends_eur",
}

_AGGREGATE_TOOL_OF = {
    "get_positions": "get_aggregate_positions",
    "get_monte_carlo": "get_aggregate_monte_carlo",
}


def t_sum_eur(n: int) -> float:
    """Somma di n importi arrotondati a 2 decimali."""
    return 0.005 * n + 0.01


# ---------------------------------------------------------------------------
# Supporto
# ---------------------------------------------------------------------------


def _tool_args(tool: str, scope: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> tuple[str, dict]:
    """Tool e argomenti effettivi di ``ctx.scoped(tool, scope, extra)`` (per le evidenze)."""
    if scope["kind"] == "aggregate":
        return _AGGREGATE_TOOL_OF[tool], {"portfolio_ids": list(scope["portfolio_ids"])}
    return tool, {"portfolio_id": scope["portfolio_id"], **dict(extra or {})}


def _ev(
    tool: str, args: Mapping[str, Any], path: str, observed: Any, expected: Any = None,
    tolerance: float | None = None, note: str | None = None,
) -> dict[str, Any]:
    return {
        "tool": tool,
        "args": dict(args),
        "path": path,
        "observed": observed,
        "expected": expected,
        "tolerance": tolerance,
        "note": note,
    }


def _pass(evidence: list[dict] | None = None) -> dict[str, Any]:
    return {"status": "pass", "reason_code": None, "reason": None, "evidence": list(evidence or [])[:MAX_EVIDENCE]}


def _skip(code: str, reason: str, evidence: list[dict] | None = None) -> dict[str, Any]:
    return {"status": "skip", "reason_code": code, "reason": reason, "evidence": list(evidence or [])[:MAX_EVIDENCE]}


def _fail(reason: str, evidence: list[dict]) -> dict[str, Any]:
    return {
        "status": "fail",
        "reason_code": "invariant_violated",
        "reason": reason,
        "evidence": list(evidence)[:MAX_EVIDENCE],
    }


def _verdict(violations: list[dict], reason: str, pass_evidence: list[dict] | None = None) -> dict[str, Any]:
    if violations:
        return _fail(f"{reason} ({len(violations)} violazioni).", violations)
    return _pass(pass_evidence)


def _num(value: Any) -> float | None:
    """Numero finito oppure None (i booleani non sono numeri)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _sel(symbol: Any) -> str:
    return f"[symbol={symbol}]"


def _positions(ctx: Any, scope: Mapping[str, Any]) -> tuple[list[dict], str, dict]:
    tool, args = _tool_args("get_positions", scope)
    rows = ctx.scoped("get_positions", scope).get("positions") or []
    return list(rows), tool, args


def _empty_skip(tool: str, args: dict) -> dict[str, Any]:
    return _skip(
        "empty_portfolio", "Il portafoglio non ha posizioni.",
        [_ev(tool, args, "positions", [], None, None, "nessuna posizione")],
    )


# ---------------------------------------------------------------------------
# Costi
# ---------------------------------------------------------------------------


def _cost_breakdown(ctx: Any, scope: Mapping[str, Any]) -> tuple[dict, dict]:
    tool, args = _tool_args("get_cost_breakdown", scope)
    return ctx.scoped("get_cost_breakdown", scope), args


def _cost_empty_skip(args: dict) -> dict[str, Any]:
    # position_costs ha una riga per ogni posizione di repo.get_positions (le prime 20):
    # vuota esattamente quando get_positions è vuoto.
    return _skip(
        "empty_portfolio", "Il portafoglio non ha posizioni.",
        [_ev("get_cost_breakdown", args, "position_costs", [], None, None, "nessuna posizione")],
    )


def check_ter_range(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-TER-RANGE: TER per riga in R_ter e TER ponderato in [0; 3]."""
    cb, args = _cost_breakdown(ctx, scope)
    tool = "get_cost_breakdown"
    rows = cb.get("position_costs") or []
    if not rows:
        return _cost_empty_skip(args)
    if not any(r.get("ter_pct") is not None for r in rows):
        return _skip(
            "no_reference_data", "Nessuna posizione ha un TER noto.",
            [_ev(tool, args, "position_costs[*].ter_pct", None, None, None, "tutti null")],
        )

    violations: list[dict] = []
    checked = 0
    for row in rows:
        source = row.get("ter_source")
        raw = row.get("ter_pct")
        ter = _num(raw)
        if source in ("justetf", "yfinance") or (source == "inferred" and ter is not None and ter > 0):
            checked += 1
            if ter is None or not (R_TER_MIN - EPS <= ter <= R_TER_MAX + EPS):
                violations.append(_ev(
                    tool, args, f"position_costs{_sel(row.get('symbol'))}.ter_pct", raw,
                    {"min": R_TER_MIN, "max": R_TER_MAX}, None,
                    f"ter_source {source}: TER fuori dall'intervallo plausibile 0,01%-3,00%",
                ))
    weighted_raw = cb.get("weighted_ter_pct")
    if weighted_raw is not None:
        weighted = _num(weighted_raw)
        if weighted is None or not (-EPS <= weighted <= WEIGHTED_TER_MAX + EPS):
            violations.append(_ev(
                tool, args, "weighted_ter_pct", weighted_raw, {"min": 0.0, "max": WEIGHTED_TER_MAX}, None,
                "TER ponderato fuori da 0%-3%",
            ))
    return _verdict(
        violations, "Alcuni TER sono fuori dall'intervallo plausibile (possibile errore di unità)",
        [_ev(tool, args, "weighted_ter_pct", weighted_raw, None, None, f"{checked} righe con TER verificate")],
    )


def check_cost_coherence(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-COST-COHERENCE: costo annuo e fee drag sul perimetro coperto con il TER medio."""
    cb, args = _cost_breakdown(ctx, scope)
    tool = "get_cost_breakdown"
    rows = cb.get("position_costs") or []
    if not rows:
        return _cost_empty_skip(args)

    violations: list[dict] = []
    weighted_raw = cb.get("weighted_ter_pct")
    known_raw = cb.get("estimated_annual_cost_known_eur")
    drag_raw = cb.get("fee_drag_10y_eur")

    if weighted_raw is None:
        for field, value in (("estimated_annual_cost_known_eur", known_raw), ("fee_drag_10y_eur", drag_raw)):
            if value is not None:
                violations.append(_ev(tool, args, field, value, None, None, "weighted_ter_pct è null"))
        return _verdict(
            violations, "Costo annuo presente senza TER medio",
            [_ev(tool, args, "weighted_ter_pct", None, None, None, "nessun TER: costi null")],
        )

    w = _num(weighted_raw)
    covered_raw = cb.get("covered_market_value_eur")
    c = _num(covered_raw)
    known = _num(known_raw)
    if w is None:
        violations.append(_ev(tool, args, "weighted_ter_pct", weighted_raw, None, None, "non numerico"))
    if c is None:
        violations.append(_ev(tool, args, "covered_market_value_eur", covered_raw, None, None, "non numerico"))
    if w is not None and c is not None:
        expected_cost = c * w / 100.0
        tol_cost = T_EUR + c * 5e-6
        if known is None or abs(known - expected_cost) > tol_cost + EPS:
            violations.append(_ev(
                tool, args, "estimated_annual_cost_known_eur", known_raw, round(expected_cost, 6), tol_cost,
                "atteso covered_market_value_eur × weighted_ter_pct / 100",
            ))
        expected_drag = c * (1.0 - (1.0 - w / 100.0) ** 10)
        tol_drag = T_EUR + c * 5e-5
        drag = _num(drag_raw)
        if drag is None or abs(drag - expected_drag) > tol_drag + EPS:
            violations.append(_ev(
                tool, args, "fee_drag_10y_eur", drag_raw, round(expected_drag, 6), tol_drag,
                "atteso covered_market_value_eur × (1 − (1 − w/100)^10)",
            ))
        total_mv_raw = cb.get("portfolio_market_value")
        total_mv = _num(total_mv_raw)
        if total_mv is None or c > total_mv + T_EUR + EPS:
            violations.append(_ev(
                tool, args, "covered_market_value_eur", covered_raw, total_mv_raw, T_EUR,
                "il valore coperto supera il valore del portafoglio",
            ))
    total_cost_raw = cb.get("total_annual_cost_eur")
    if total_cost_raw != known_raw:
        violations.append(_ev(
            tool, args, "total_annual_cost_eur", total_cost_raw, known_raw, None,
            "chiave legacy: deve valere estimated_annual_cost_known_eur",
        ))
    row_costs = [_num(r.get("annual_cost_eur")) for r in rows if r.get("annual_cost_eur") is not None]
    if known is not None:
        row_sum = sum(x for x in row_costs if x is not None)
        tol_rows = t_sum_eur(len(rows))
        if row_sum > known + tol_rows + EPS:
            violations.append(_ev(
                tool, args, "position_costs[*].annual_cost_eur", round(row_sum, 6), known_raw, tol_rows,
                "somma: le righe superano il costo annuo stimato",
            ))
    if cb.get("cost_perimeter") != "covered_positions":
        violations.append(_ev(
            tool, args, "cost_perimeter", cb.get("cost_perimeter"), "covered_positions", None,
            "perimetro dei costi non dichiarato",
        ))
    return _verdict(
        violations, "Il costo annuo stimato non è coerente con il TER medio e il valore coperto",
        [_ev(tool, args, "estimated_annual_cost_known_eur", known_raw, None, None,
             f"TER {weighted_raw}% su {covered_raw} € coperti")],
    )


def check_cost_coverage_declared(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-COST-COVERAGE-DECLARED: TER mancanti e dedotti dichiarati."""
    cb, args = _cost_breakdown(ctx, scope)
    tool = "get_cost_breakdown"
    rows = cb.get("position_costs") or []
    if not rows:
        return _cost_empty_skip(args)

    violations: list[dict] = []
    missing_raw = cb.get("missing_ter_symbols")
    missing = list(missing_raw) if isinstance(missing_raw, list) else []
    if not isinstance(missing_raw, list):
        violations.append(_ev(tool, args, "missing_ter_symbols", missing_raw, [], None, "elenco assente"))
    inferred_raw = cb.get("inferred_ter_symbols")
    inferred = list(inferred_raw) if isinstance(inferred_raw, list) else []
    if not isinstance(inferred_raw, list):
        violations.append(_ev(tool, args, "inferred_ter_symbols", inferred_raw, [], None, "elenco assente"))
    coverage_raw = cb.get("ter_coverage_pct")
    coverage = _num(coverage_raw)
    incomplete = coverage is not None and coverage < 100.0

    if bool(missing) != incomplete:
        violations.append(_ev(
            tool, args, "missing_ter_symbols", missing_raw, None, None,
            f"ter_coverage_pct = {coverage_raw}: i TER mancanti devono essere elencati se e solo se la copertura è < 100",
        ))
    if incomplete:
        note = cb.get("coverage_note")
        if not isinstance(note, str) or not note.strip():
            violations.append(_ev(
                tool, args, "coverage_note", note, None, None, "copertura incompleta senza nota",
            ))
        else:
            for symbol in missing:
                if str(symbol) not in note:
                    violations.append(_ev(
                        tool, args, "coverage_note", note, symbol, None, "simbolo mancante non citato nella nota",
                    ))
    for row in rows:
        symbol = row.get("symbol")
        if row.get("ter_pct") is None and symbol not in missing:
            violations.append(_ev(
                tool, args, f"position_costs{_sel(symbol)}.ter_pct", None, None, None,
                "TER mancante non elencato in missing_ter_symbols",
            ))
        if row.get("ter_source") == "inferred" and symbol not in inferred:
            violations.append(_ev(
                tool, args, f"position_costs{_sel(symbol)}.ter_source", "inferred", None, None,
                "TER dedotto non elencato in inferred_ter_symbols",
            ))
    return _verdict(
        violations, "La copertura incompleta dei TER non è dichiarata",
        [_ev(tool, args, "ter_coverage_pct", coverage_raw, None, None, f"mancanti: {missing}")],
    )


# ---------------------------------------------------------------------------
# Reddito
# ---------------------------------------------------------------------------


def check_income_buckets_sum(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-INCOME-BUCKETS-SUM: bucket = lordo, netto con l'aliquota, proiezioni 1/3/5."""
    rows, ptool, pargs = _positions(ctx, scope)
    if not rows:
        return _empty_skip(ptool, pargs)
    tool, args = _tool_args("get_income_projection", scope)
    inc = ctx.scoped("get_income_projection", scope)

    violations: list[dict] = []
    gross_raw = inc.get("current_annual_dividends_gross_eur")
    gross = _num(gross_raw)
    buckets = [_num(inc.get(f)) for f in INCOME_BUCKET_FIELDS.values()]
    if gross is None or any(b is None for b in buckets):
        violations.append(_ev(
            tool, args, "current_annual_dividends_gross_eur", gross_raw, None, None,
            "lordo o bucket non numerici: " + ", ".join(f"{f}={inc.get(f)!r}" for f in INCOME_BUCKET_FIELDS.values()),
        ))
    else:
        bucket_sum = sum(buckets)  # type: ignore[arg-type]
        if abs(bucket_sum - gross) > INCOME_BUCKETS_TOL + EPS:
            violations.append(_ev(
                tool, args, "equity_annual_dividends_eur+fixed_income_annual_dividends_eur+other_or_unknown_annual_dividends_eur",
                round(bucket_sum, 6), gross_raw, INCOME_BUCKETS_TOL, "somma dei bucket contro il lordo",
            ))
    tax_raw = inc.get("tax_rate_pct")
    tax = _num(tax_raw)
    net_raw = inc.get("current_annual_dividends_net_eur")
    net = _num(net_raw)
    if gross is not None:
        if tax is None or net is None:
            violations.append(_ev(tool, args, "current_annual_dividends_net_eur", net_raw, None, None,
                                  f"netto o aliquota non numerici (tax_rate_pct={tax_raw!r})"))
        else:
            expected_net = gross * (1.0 - tax / 100.0)
            if abs(net - expected_net) > T_EUR + EPS:
                violations.append(_ev(
                    tool, args, "current_annual_dividends_net_eur", net_raw, round(expected_net, 6), T_EUR,
                    f"lordo × (1 − {tax_raw}/100)",
                ))
    projections = inc.get("projections") or []
    years = [p.get("years") for p in projections]
    if years != INCOME_PROJECTION_YEARS:
        violations.append(_ev(tool, args, "projections[*].years", years, INCOME_PROJECTION_YEARS, None, None))
    for p in projections:
        cg_raw, cn_raw = p.get("cumulative_gross_eur"), p.get("cumulative_net_eur")
        cg, cn = _num(cg_raw), _num(cn_raw)
        if cg is None or cn is None or cn > cg + T_EUR + EPS:
            violations.append(_ev(
                tool, args, f"projections[years={p.get('years')}].cumulative_net_eur", cn_raw, cg_raw, T_EUR,
                "il netto cumulato supera il lordo cumulato",
            ))
    return _verdict(
        violations, "Il reddito stimato per classe non torna con il reddito totale",
        [_ev(tool, args, "current_annual_dividends_gross_eur", gross_raw, None, None, "somma dei bucket verificata")],
    )


def check_income_class_recompute(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-INCOME-CLASS-RECOMPUTE: ricalcolo dei bucket dalla classe di ``search_asset_info``."""
    rows, ptool, pargs = _positions(ctx, scope)
    if not rows:
        return _empty_skip(ptool, pargs)
    if len(rows) >= POSITIONS_ROW_LIMIT:
        return _skip(
            "truncated_output", "Le posizioni sono troncate a 30 righe: il ricalcolo non è completo.",
            [_ev(ptool, pargs, "positions", len(rows), None, None, "righe restituite")],
        )

    violations: list[dict] = []
    recomputed = {bucket: 0.0 for bucket in INCOME_BUCKET_FIELDS}
    contributors = 0
    for row in rows:
        symbol = row.get("symbol")
        stool, sargs = _tool_args("search_asset_info", scope, {"symbol": symbol})
        info = ctx.scoped("search_asset_info", scope, {"symbol": symbol})
        if "error" in info:
            violations.append(_ev(stool, sargs, "error", info.get("error"), None, None,
                                  "informazioni dello strumento non disponibili"))
            continue
        dy = _num(info.get("dividend_yield"))
        if dy is None or dy <= 0:
            continue
        mv = _num(row.get("market_value"))
        if mv is None:
            violations.append(_ev(ptool, pargs, f"positions{_sel(symbol)}.market_value", row.get("market_value"),
                                  None, None, "valore non numerico"))
            continue
        contributors += 1
        asset_class = info.get("asset_class")
        bucket = {"equity": "equity", "bond": "fixed_income"}.get(asset_class, "other_or_unknown")
        recomputed[bucket] += mv * dy / 100.0

    if contributors == 0 and not violations:
        return _skip(
            "no_reference_data", "Nessuna posizione ha un rendimento da dividendi noto.",
            [_ev(ptool, pargs, "positions", len(rows), None, None, "nessun dividend_yield > 0")],
        )

    tool, args = _tool_args("get_income_projection", scope)
    inc = ctx.scoped("get_income_projection", scope)
    for bucket, field in INCOME_BUCKET_FIELDS.items():
        expected = recomputed[bucket]
        tol = T_EUR + 1e-6 * expected
        observed_raw = inc.get(field)
        observed = _num(observed_raw)
        if observed is None or abs(observed - expected) > tol + EPS:
            violations.append(_ev(
                tool, args, field, observed_raw, round(expected, 6), tol,
                "ricalcolo: market_value × dividend_yield / 100 per classe di search_asset_info",
            ))
    return _verdict(
        violations, "Il reddito non è attribuito alle classi di attivo corrette",
        [_ev(tool, args, field, inc.get(field), round(recomputed[b], 6), T_EUR, None)
         for b, field in INCOME_BUCKET_FIELDS.items()],
    )


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------


def _monte_carlo(ctx: Any, scope: Mapping[str, Any]) -> tuple[dict | None, dict, str, dict]:
    """(skip, output, tool, args): skip se il portafoglio è vuoto o non c'è storico."""
    rows, ptool, pargs = _positions(ctx, scope)
    if not rows:
        return _empty_skip(ptool, pargs), {}, "", {}
    tool, args = _tool_args("get_monte_carlo", scope)
    mc = ctx.scoped("get_monte_carlo", scope)
    if not (mc.get("projections") or []):
        return _skip(
            "no_history", "Senza storico dei prezzi la proiezione Monte Carlo è vuota.",
            [_ev(tool, args, "projections", [], None, None, None)],
        ), mc, tool, args
    return None, mc, tool, args


def check_mc_years(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-MC-YEARS: anni 1..10, indice base 100."""
    skip, mc, tool, args = _monte_carlo(ctx, scope)
    if skip:
        return skip
    violations: list[dict] = []
    years = [p.get("year") for p in mc["projections"]]
    if years != MC_YEARS:
        violations.append(_ev(tool, args, "projections[*].year", years, MC_YEARS, None, "anni della proiezione"))
    if mc.get("unit") != "indice_base_100":
        violations.append(_ev(tool, args, "unit", mc.get("unit"), "indice_base_100", None, None))
    if mc.get("initial_value") != 100:
        violations.append(_ev(tool, args, "initial_value", mc.get("initial_value"), 100, None, None))
    return _verdict(
        violations, "La proiezione Monte Carlo non copre esattamente gli anni da 1 a 10 in indice base 100",
        [_ev(tool, args, "projections[*].year", years, MC_YEARS, None, None)],
    )


def check_mc_percentiles(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-MC-PERCENTILES: 0 < p25 ≤ p50 ≤ p75 per ogni anno."""
    skip, mc, tool, args = _monte_carlo(ctx, scope)
    if skip:
        return skip
    violations: list[dict] = []
    for p in mc["projections"]:
        raw = [p.get("p25"), p.get("p50"), p.get("p75")]
        p25, p50, p75 = (_num(v) for v in raw)
        if p25 is None or p50 is None or p75 is None or not (0 < p25 <= p50 <= p75):
            violations.append(_ev(
                tool, args, f"projections[year={p.get('year')}]", {"p25": raw[0], "p50": raw[1], "p75": raw[2]},
                None, None, "atteso 0 < p25 ≤ p50 ≤ p75",
            ))
    return _verdict(violations, "I percentili della proiezione Monte Carlo non sono ordinati",
                    [_ev(tool, args, "projections[*]", len(mc["projections"]), None, None, "anni verificati")])


def check_mc_median_drift(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-MC-MEDIAN-DRIFT: p50 ≈ 100 × (1 + μ)^anno."""
    skip, mc, tool, args = _monte_carlo(ctx, scope)
    if skip:
        return skip
    mu_raw = mc.get("annualized_mean_return_pct")
    mu = _num(mu_raw)
    if mu is None:
        return _fail("Rendimento atteso della proiezione non numerico.", [
            _ev(tool, args, "annualized_mean_return_pct", mu_raw, None, None, None),
        ])
    violations: list[dict] = []
    for p in mc["projections"]:
        year = p.get("year")
        p50 = _num(p.get("p50"))
        y = _num(year)
        if y is None or p50 is None:
            violations.append(_ev(tool, args, f"projections[year={year}].p50", p.get("p50"), None, T_MC,
                                  "anno o mediana non numerici"))
            continue
        expected = 100.0 * (1.0 + mu / 100.0) ** y
        if expected <= 0 or abs(p50 / expected - 1.0) > T_MC + EPS:
            violations.append(_ev(
                tool, args, f"projections[year={year}].p50", p.get("p50"), round(expected, 4), T_MC,
                f"100 × (1 + {mu_raw}/100)^{year}, tolleranza relativa",
            ))
    return _verdict(violations, "La mediana della proiezione non segue il rendimento atteso dichiarato",
                    [_ev(tool, args, "annualized_mean_return_pct", mu_raw, None, None, None)])


# ---------------------------------------------------------------------------
# Dividendi
# ---------------------------------------------------------------------------


def check_dividend_currency(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-DIV-CURRENCY: totali per valuta ricalcolati dalle transazioni ``dividend``."""
    pid = scope["portfolio_id"]
    tx_args = {"portfolio_id": pid}
    dividends = [t for t in ctx.transactions(pid) if t.get("side") == "dividend"]
    if not dividends:
        return _skip(
            "no_reference_data", "Nessun dividendo registrato nel portafoglio.",
            [_ev("ctx.transactions", tx_args, "[side=dividend]", 0, None, None, "conteggio")],
        )

    recomputed: dict[str, dict[str, float]] = {}
    for t in dividends:
        ccy = str(t.get("trade_currency") or "").upper() or "N/D"
        bucket = recomputed.setdefault(ccy, {"total": 0.0, "count": 0})
        bucket["total"] += float(t.get("quantity") or 0.0) * float(t.get("price") or 0.0)
        bucket["count"] += 1

    tool, args = _tool_args("get_dividend_summary", scope)
    ds = ctx.scoped("get_dividend_summary", scope)
    violations: list[dict] = []
    by_raw = ds.get("dividends_by_currency")
    by = by_raw if isinstance(by_raw, dict) else {}
    if sorted(by) != sorted(recomputed):
        violations.append(_ev(
            tool, args, "dividends_by_currency", sorted(by) if isinstance(by_raw, dict) else by_raw,
            sorted(recomputed), None, "valute dei dividendi (chiavi)",
        ))
        violations.append(_ev("ctx.transactions", tx_args, "[side=dividend].trade_currency", sorted(recomputed),
                              None, None, "valute ricalcolate"))
    for ccy, ref in sorted(recomputed.items()):
        entry = by.get(ccy)
        if not isinstance(entry, dict):
            continue
        total = _num(entry.get("total"))
        if total is None or abs(total - ref["total"]) > T_EUR + EPS:
            violations.append(_ev(
                tool, args, f"dividends_by_currency.{ccy}.total", entry.get("total"), round(ref["total"], 6), T_EUR,
                "Σ quantity × price delle transazioni dividend",
            ))
        if entry.get("count") != ref["count"]:
            violations.append(_ev(tool, args, f"dividends_by_currency.{ccy}.count", entry.get("count"),
                                  ref["count"], None, None))
    if ds.get("dividend_transactions_count") != len(dividends):
        violations.append(_ev(tool, args, "dividend_transactions_count", ds.get("dividend_transactions_count"),
                              len(dividends), None, None))
    mixed = len(recomputed) > 1
    if ds.get("mixed_currencies") is not mixed:
        violations.append(_ev(tool, args, "mixed_currencies", ds.get("mixed_currencies"), mixed, None,
                              f"valute: {sorted(recomputed)}"))
    if mixed:
        for field in ("total_dividends_received", "dividends_last_12m", "dividends_currency"):
            if ds.get(field) is not None:
                violations.append(_ev(tool, args, field, ds.get(field), None, None,
                                      "con più valute il totale unico deve essere null"))
        note = ds.get("currency_note")
        if not isinstance(note, str) or not note.strip():
            violations.append(_ev(tool, args, "currency_note", note, None, None, "nota sulle valute assente"))
    else:
        (ccy, ref), = recomputed.items()
        total_raw = ds.get("total_dividends_received")
        total = _num(total_raw)
        if total is None or abs(total - ref["total"]) > T_EUR + EPS:
            violations.append(_ev(tool, args, "total_dividends_received", total_raw, round(ref["total"], 6), T_EUR,
                                  f"totale della sola valuta {ccy}"))
        if ds.get("dividends_currency") != ccy:
            violations.append(_ev(tool, args, "dividends_currency", ds.get("dividends_currency"), ccy, None, None))
    return _verdict(
        violations, "I dividendi non sono totalizzati correttamente per valuta",
        [_ev(tool, args, "dividends_by_currency", sorted(by), sorted(recomputed), None, None)],
    )


# ---------------------------------------------------------------------------
# Variazioni giornaliere
# ---------------------------------------------------------------------------


def _mover_change(mover: Any) -> float | None:
    return _num(mover.get("day_change_pct")) if isinstance(mover, dict) else None


def check_daymovers_nonzero_included(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-DAYMOVERS-NONZERO-INCLUDED: le variazioni non nulle stanno fra peggiore e migliore."""
    rows, ptool, pargs = _positions(ctx, scope)
    if not rows:
        return _empty_skip(ptool, pargs)
    fresh = [
        r for r in rows
        if not r.get("price_stale") and r.get("price_date") is not None
        and _num(r.get("day_change_pct")) is not None and _num(r.get("day_change_pct")) != 0
    ]
    if not fresh:
        return _skip(
            "no_reference_data",
            "Nessuna variazione giornaliera disponibile (mercato chiuso, giornata piatta o nessuna chiusura precedente).",
            [_ev(ptool, pargs, "positions[*].day_change_pct", 0, None, None, "nessuna variazione non nulla")],
        )

    tool, args = _tool_args("get_day_movers", scope)
    dm = ctx.scoped("get_day_movers", scope)
    violations: list[dict] = []
    valid = dm.get("valid_positions")
    if isinstance(valid, bool) or not isinstance(valid, int) or valid < 1:
        violations.append(_ev(tool, args, "valid_positions", valid, None, None,
                              f"{len(fresh)} posizioni con variazione non nulla"))
    best, worst = dm.get("best"), dm.get("worst")
    hi, lo = _mover_change(best), _mover_change(worst)
    if hi is None:
        violations.append(_ev(tool, args, "best", best, None, None, "migliore assente con variazioni disponibili"))
    if lo is None:
        violations.append(_ev(tool, args, "worst", worst, None, None, "peggiore assente con variazioni disponibili"))
    if hi is not None and lo is not None:
        for r in fresh:
            change = _num(r.get("day_change_pct"))
            if not (lo - T_PP - EPS <= change <= hi + T_PP + EPS):  # type: ignore[operator]
                violations.append(_ev(
                    ptool, pargs, f"positions{_sel(r.get('symbol'))}.day_change_pct", r.get("day_change_pct"),
                    {"min": lo, "max": hi}, T_PP, "fuori dall'intervallo peggiore-migliore di get_day_movers",
                ))
    if violations:
        violations.append(_ev(ptool, pargs, "positions[*].day_change_pct",
                              {str(r.get("symbol")): r.get("day_change_pct") for r in fresh}, None, None,
                              "variazioni non nulle con prezzo aggiornato"))
    return _verdict(violations, "Le variazioni giornaliere disponibili non compaiono fra migliori e peggiori",
                    [_ev(tool, args, "valid_positions", valid, None, None, None)])


def check_daymovers_consistency(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-DAYMOVERS-CONSISTENCY: esclusioni dichiarate e coerenti con le posizioni."""
    rows, ptool, pargs = _positions(ctx, scope)
    if not rows:
        return _empty_skip(ptool, pargs)
    tool, args = _tool_args("get_day_movers", scope)
    dm = ctx.scoped("get_day_movers", scope)
    violations: list[dict] = []

    def _count(field: str) -> int | None:
        value = dm.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            violations.append(_ev(tool, args, field, value, None, None, "conteggio assente o non valido"))
            return None
        return value

    valid = _count("valid_positions")
    best, worst = dm.get("best"), dm.get("worst")
    if valid is not None and not ((best is None) == (worst is None) == (valid == 0)):
        violations.append(_ev(tool, args, "best/worst/valid_positions",
                              {"best": best, "worst": worst, "valid_positions": valid}, None, None,
                              "best null ⇔ worst null ⇔ valid_positions = 0"))
    if best is None:
        reason = dm.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            violations.append(_ev(tool, args, "reason", reason, None, None, "nessun motivo per best null"))
    if valid is not None and valid >= 1 and isinstance(best, dict) and isinstance(worst, dict):
        hi, lo = _mover_change(best), _mover_change(worst)
        if hi is None or lo is None or hi < lo:
            violations.append(_ev(tool, args, "best.day_change_pct", best.get("day_change_pct"),
                                  worst.get("day_change_pct"), None, "migliore < peggiore"))
        stale_raw = dm.get("stale_positions")
        stale_symbols = {s.get("symbol") for s in stale_raw if isinstance(s, dict)} if isinstance(stale_raw, list) else set()
        row_by_symbol = {r.get("symbol"): r for r in rows}
        for label, mover in (("best", best), ("worst", worst)):
            symbol = mover.get("symbol")
            if symbol in stale_symbols:
                violations.append(_ev(tool, args, f"{label}.symbol", symbol, None, None,
                                      "simbolo presente fra le quotazioni ferme (stale_positions)"))
            row = row_by_symbol.get(symbol)
            if row is not None and row.get("price_stale"):
                violations.append(_ev(ptool, pargs, f"positions{_sel(symbol)}.price_stale", True, False, None,
                                      f"{label} di get_day_movers su una quotazione ferma"))
        if valid == 1 and best.get("symbol") != worst.get("symbol"):
            violations.append(_ev(tool, args, "worst.symbol", worst.get("symbol"), best.get("symbol"), None,
                                  "con una sola posizione valida migliore e peggiore coincidono"))
    if len(rows) < POSITIONS_ROW_LIMIT:
        excluded_stale = _count("excluded_stale")
        excluded_no_prev = _count("excluded_no_previous_close")
        if None not in (valid, excluded_stale, excluded_no_prev):
            total = valid + excluded_stale + excluded_no_prev  # type: ignore[operator]
            if total != len(rows):
                violations.append(_ev(
                    tool, args, "valid_positions+excluded_stale+excluded_no_previous_close", total, len(rows), None,
                    "somma: ogni posizione deve essere valida o esclusa con motivo",
                ))
                violations.append(_ev(ptool, pargs, "positions", len(rows), None, None, "righe"))
    return _verdict(
        violations, "Migliori e peggiori del giorno non escludono in modo dichiarato le quotazioni non valide",
        [_ev(tool, args, "valid_positions", valid, None, None, f"{len(rows)} posizioni")],
    )


# Errore ammesso su day_change_pct del riepilogo (rules.md, C-DAYCHANGE-DENOMINATOR): T_pp più l'errore sul
# denominatore ricostruito da variazioni delle posizioni arrotondate a 2 decimali e da day_change a 2 decimali.
T_DAYCHANGE_PP = 0.01


def check_daychange_denominator(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    """C-DAYCHANGE-DENOMINATOR: ``day_change_pct`` del riepilogo è calcolata su tutte le posizioni.

    Denominatore ricostruito dalle righe di ``get_positions``: P = Σ market_value / (1 + day_change_pct / 100).
    Una riga senza chiusura precedente ha variazione 0 e conta col suo valore, come una quotazione ferma.
    """
    rows, ptool, pargs = _positions(ctx, scope)
    if not rows:
        return _empty_skip(ptool, pargs)
    if len(rows) >= POSITIONS_ROW_LIMIT:
        return _skip(
            "truncated_output", "Le posizioni sono troncate a 30 righe: il denominatore non è completo.",
            [_ev(ptool, pargs, "positions", len(rows), None, None, "righe restituite")],
        )
    stool, sargs = _tool_args("get_portfolio_summary", scope)
    summary = ctx.scoped("get_portfolio_summary", scope)
    base = summary.get("base_currency")
    # La variazione della posizione è in valuta di quotazione, quella del riepilogo al cambio: il
    # ricalcolo vale solo se tutte le posizioni sono quotate nella valuta base.
    foreign: dict[str, Any] = {}
    for row in rows:
        symbol = row.get("symbol")
        info = ctx.scoped("search_asset_info", scope, {"symbol": symbol})
        currency = info.get("currency") if isinstance(info, dict) else None
        if not isinstance(base, str) or currency != base:
            foreign[str(symbol)] = currency
    if foreign:
        return _skip(
            "not_applicable",
            "Alcune posizioni non sono quotate nella valuta base: la variazione della posizione non include il cambio.",
            [_ev("search_asset_info", {**sargs, "symbol": symbol}, "currency", currency, base, None,
                 "valuta di quotazione diversa dalla base") for symbol, currency in sorted(foreign.items())],
        )

    day_change = _num(summary.get("day_change"))
    observed = _num(summary.get("day_change_pct"))
    previous = 0.0
    changes = 0
    violations: list[dict] = []
    for row in rows:
        symbol = row.get("symbol")
        mv, pct = _num(row.get("market_value")), _num(row.get("day_change_pct"))
        if mv is None or pct is None or pct <= -100.0:
            violations.append(_ev(ptool, pargs, f"positions{_sel(symbol)}", {"market_value": row.get("market_value"),
                                  "day_change_pct": row.get("day_change_pct")}, None, None,
                                  "valore o variazione non validi"))
            continue
        if pct != 0:
            changes += 1
        previous += mv / (1.0 + pct / 100.0)
    if day_change is None or observed is None:
        violations.append(_ev(stool, sargs, "day_change_pct", summary.get("day_change_pct"), None, None,
                              "variazione del riepilogo assente o non numerica"))
    if violations:
        return _fail("I dati della variazione giornaliera non sono validi.", violations)
    if day_change == 0 and changes == 0:
        return _skip(
            "no_reference_data", "Nessuna variazione giornaliera nel portafoglio (mercato chiuso o giornata piatta).",
            [_ev(stool, sargs, "day_change", day_change, None, None, "nessuna variazione")],
        )
    if abs(previous) <= EPS:
        return _skip(
            "no_reference_data", "Il valore precedente delle posizioni è nullo: la percentuale non è definita.",
            [_ev(ptool, pargs, "positions[*].market_value", round(previous, 2), None, None, "valore precedente")],
        )
    expected = day_change / previous * 100.0  # type: ignore[operator]
    evidence = [
        _ev(stool, sargs, "day_change_pct", observed, round(expected, 4), T_DAYCHANGE_PP,
            f"day_change {day_change} / valore precedente {round(previous, 2)}"),
        _ev(ptool, pargs, "positions[*].market_value", round(sum(_num(r.get("market_value")) or 0.0 for r in rows), 2),
            round(previous, 2), None, "somma: valore attuale e valore precedente (market_value / (1 + variazione))"),
    ]
    if abs(observed - expected) > T_DAYCHANGE_PP + EPS:  # type: ignore[operator]
        return _fail(
            "La variazione giornaliera percentuale del portafoglio non è calcolata sul valore di tutte le posizioni.",
            evidence,
        )
    return _pass(evidence)


# ---------------------------------------------------------------------------
# Dichiarazioni (rules.md §4)
# ---------------------------------------------------------------------------

RULES: list[dict[str, Any]] = [
    {
        "id": "C-TER-RANGE",
        "group": "C",
        "title": "I costi annui dei fondi (TER) sono in un intervallo plausibile",
        "area": "costs",
        "severity": "P1",
        "findings": ["V-TER-UNIT", "V365-007"],
        "scopes": ["portfolio"],
        "tools": ["get_cost_breakdown"],
        "check": check_ter_range,
    },
    {
        "id": "C-COST-COHERENCE",
        "group": "C",
        "title": "Il costo annuo stimato è coerente con il TER medio e il valore coperto",
        "area": "costs",
        "severity": "P1",
        "findings": ["V365-007"],
        "scopes": ["portfolio"],
        "tools": ["get_cost_breakdown"],
        "check": check_cost_coherence,
    },
    {
        "id": "C-COST-COVERAGE-DECLARED",
        "group": "C",
        "title": "Quando mancano dei TER, la copertura incompleta è dichiarata",
        "area": "costs",
        "severity": "P1",
        "findings": ["V365-007"],
        "scopes": ["portfolio"],
        "tools": ["get_cost_breakdown"],
        "check": check_cost_coverage_declared,
    },
    {
        "id": "C-INCOME-BUCKETS-SUM",
        "group": "C",
        "title": "Il reddito stimato per classe somma al reddito totale",
        "area": "income",
        "severity": "P1",
        "findings": ["V365-004"],
        "scopes": ["portfolio"],
        # get_positions: solo per riconoscere il portafoglio vuoto (rules.md §0.3; Deviazioni TASK-76).
        "tools": ["get_income_projection", "get_positions"],
        "check": check_income_buckets_sum,
    },
    {
        "id": "C-INCOME-CLASS-RECOMPUTE",
        "group": "C",
        "title": "Il reddito degli ETF obbligazionari è conteggiato come reddito fisso, non azionario",
        "area": "income",
        "severity": "P1",
        "findings": ["V365-004", "V-INCOME-TYPE"],
        "scopes": ["portfolio"],
        "tools": ["get_positions", "search_asset_info", "get_income_projection"],
        "check": check_income_class_recompute,
    },
    {
        "id": "C-MC-YEARS",
        "group": "C",
        "title": "La proiezione Monte Carlo copre esattamente gli anni da 1 a 10, come indice base 100",
        "area": "montecarlo",
        "severity": "P1",
        "findings": ["V365-006"],
        "scopes": ["portfolio", "aggregate"],
        "tools": ["get_monte_carlo", "get_aggregate_monte_carlo", "get_positions", "get_aggregate_positions"],
        "check": check_mc_years,
    },
    {
        "id": "C-MC-PERCENTILES",
        "group": "C",
        "title": "I percentili della proiezione Monte Carlo sono ordinati",
        "area": "montecarlo",
        "severity": "P1",
        "findings": ["V365-006"],
        "scopes": ["portfolio", "aggregate"],
        # get_positions: skip «come C-MC-YEARS» (Deviazioni TASK-76).
        "tools": ["get_monte_carlo", "get_aggregate_monte_carlo", "get_positions", "get_aggregate_positions"],
        "check": check_mc_percentiles,
    },
    {
        "id": "C-MC-MEDIAN-DRIFT",
        "group": "C",
        "title": "La mediana della proiezione segue il rendimento atteso dichiarato",
        "area": "montecarlo",
        "severity": "P2",
        "findings": ["V365-006"],
        "scopes": ["portfolio", "aggregate"],
        # get_positions: skip «come C-MC-YEARS» (Deviazioni TASK-76).
        "tools": ["get_monte_carlo", "get_aggregate_monte_carlo", "get_positions", "get_aggregate_positions"],
        "check": check_mc_median_drift,
    },
    {
        "id": "C-DIV-CURRENCY",
        "group": "C",
        "title": "I dividendi incassati sono totalizzati per valuta, senza sommare valute diverse",
        "area": "income",
        "severity": "P2",
        "findings": ["V-DIV-MIXED-CCY", "V365-009"],
        "scopes": ["portfolio"],
        "tools": ["get_dividend_summary", "ctx.transactions"],
        "check": check_dividend_currency,
    },
    {
        "id": "C-DAYMOVERS-NONZERO-INCLUDED",
        "group": "C",
        "title": "Le variazioni giornaliere disponibili compaiono fra migliori e peggiori",
        "area": "daily",
        "severity": "P1",
        "findings": ["V365-005", "V-DAYMOVERS-ROOT"],
        "scopes": ["portfolio"],
        "tools": ["get_positions", "get_day_movers"],
        "check": check_daymovers_nonzero_included,
    },
    {
        "id": "C-DAYMOVERS-CONSISTENCY",
        "group": "C",
        "title": "Migliori e peggiori del giorno escludono le quotazioni ferme e senza chiusura precedente",
        "area": "daily",
        "severity": "P1",
        "findings": ["V-DAYMOVERS-ROOT", "V365-005"],
        "scopes": ["portfolio"],
        "tools": ["get_positions", "get_day_movers"],
        "check": check_daymovers_consistency,
    },
    {
        "id": "C-DAYCHANGE-DENOMINATOR",
        "group": "C",
        "title": "La variazione giornaliera del portafoglio è calcolata su tutte le posizioni",
        "area": "daily",
        "severity": "P2",
        "findings": ["S-2026-11-11-03"],
        # Solo portfolio: search_asset_info (valuta di quotazione) non ha una variante aggregata
        # (Deviazioni TASK-86).
        "scopes": ["portfolio"],
        "tools": ["get_portfolio_summary", "get_positions", "search_asset_info"],
        "check": check_daychange_denominator,
    },
]
