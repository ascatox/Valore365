"""Auditor — gruppo A: stress test e classificazione degli strumenti (TASK-74).

Contratto: ``docs/auditor/architecture.md`` (§3.2 dichiarazione, §3.3 esito,
§3.4 scope, §5.2 argomenti canonici) e ``docs/auditor/rules.md`` §2 (schede
A-*, tolleranze in §0.2, comportamenti comuni in §0.3).

Le regole sono funzioni pure ``check(ctx, scope) -> dict``: leggono i dati
solo tramite il contesto (``ctx.call`` / ``ctx.scoped``), non catturano le
eccezioni dei tool e non importano il motore. Le tabelle di riferimento
(shock e proxy) si leggono da ``app.constants.stress_scenarios``.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping

from app.constants.stress_scenarios import (
    HISTORICAL_CLASS_PROXIES,
    HISTORICAL_MIN_COVERAGE_PCT,
    HISTORICAL_SCENARIOS,
    SHOCK_SCENARIOS,
)

# --- Tolleranze (rules.md §0.2) ---------------------------------------------

EPS = 1e-9
T_PP = 0.005           # percentuale a 2 decimali contro valore esatto
T_PP2 = 0.02           # percentuali derivate da altre già arrotondate
T_EQUAL_IMPACT = 0.01  # A-STRESS-HIST-DISTINCT: impatti a 2 decimali
COMPOSITION_L1_PP = 1.0  # A-STRESS-HIST-DISTINCT: soglia di composizione
MAX_EVIDENCE = 50

GLOBAL_EQUITY_CRASH = "Global Equity Crash"
UNKNOWN_SHOCK_FLAG = "unknown_asset_class_equity_shock"
CLASS_PROXY_FLAG = "class_proxy_drawdowns"


def T_sum_pp(n: int) -> float:
    """Somma di n percentuali arrotondate confrontata con un totale arrotondato."""
    return 0.005 * n + 0.005


HISTORICAL_BY_NAME: dict[str, dict[str, Any]] = {s["name"]: s for s in HISTORICAL_SCENARIOS}
SHOCK_BY_NAME: dict[str, dict[str, Any]] = {s["name"]: s for s in SHOCK_SCENARIOS}


# --- Supporto ---------------------------------------------------------------


def _ev(tool: str, args: Mapping[str, Any], path: str, observed: Any, expected: Any = None,
        tolerance: float | None = None, note: str | None = None) -> dict[str, Any]:
    return {
        "tool": tool,
        "args": dict(args),
        "path": path,
        "observed": observed,
        "expected": expected,
        "tolerance": tolerance,
        "note": note,
    }


def _pass(evidence: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    return {"status": "pass", "reason_code": None, "reason": None,
            "evidence": list(evidence)[:MAX_EVIDENCE]}


def _fail(reason: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "fail", "reason_code": "invariant_violated", "reason": reason,
            "evidence": evidence[:MAX_EVIDENCE]}


def _skip(code: str, reason: str, evidence: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    return {"status": "skip", "reason_code": code, "reason": reason,
            "evidence": list(evidence)[:MAX_EVIDENCE]}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _close(observed: Any, expected: float, tolerance: float) -> bool:
    value = _num(observed)
    return value is not None and abs(value - expected) <= tolerance + EPS


def _stress_call(scope: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Tool e argomenti effettivi di ``ctx.scoped("get_stress_test", scope)`` (architettura §3.5)."""
    if scope["kind"] == "aggregate":
        return "get_aggregate_stress_test", {"portfolio_ids": list(scope["portfolio_ids"])}
    return "get_stress_test", {"portfolio_id": scope["portfolio_id"]}


def _scenarios(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = result.get("scenarios")
    return [s for s in value if isinstance(s, dict)] if isinstance(value, list) else []


def _spath(scenario: Mapping[str, Any], suffix: str = "") -> str:
    path = f"scenarios[scenario_name={scenario.get('scenario_name')}]"
    return f"{path}.{suffix}" if suffix else path


def _rows(scenario: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = scenario.get("class_breakdown")
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


def _flags(scenario: Mapping[str, Any]) -> list[Any]:
    value = scenario.get("flags")
    return list(value) if isinstance(value, list) else []


def _unknown_name_evidence(tool: str, args: Mapping[str, Any], scenario: Mapping[str, Any],
                           table: Mapping[str, Any], table_name: str) -> dict[str, Any]:
    return _ev(tool, args, _spath(scenario, "scenario_name"), scenario.get("scenario_name"),
               sorted(table), None, f"scenario non previsto dalla tabella approvata {table_name}")


def _historical(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in scenarios if s.get("scenario_type") == "historical"]


def _shock(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in scenarios if s.get("scenario_type") == "shock"]


EMPTY_REASON = "Portafoglio senza posizioni: nessuno scenario da verificare."


# --- A-STRESS-HIST-DISTINCT -------------------------------------------------


def check_stress_hist_distinct(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    eligible: list[dict[str, Any]] = []
    missing_gec: list[dict[str, Any]] = []
    for pid in scope["portfolio_ids"]:
        args = {"portfolio_id": pid}
        scenarios = _scenarios(ctx.call("get_stress_test", args))
        computed = {
            s.get("scenario_name"): _num(s.get("estimated_portfolio_impact_pct"))
            for s in _historical(scenarios)
            if s.get("method") != "not_available"
        }
        if not computed:
            continue
        gec = next((s for s in _shock(scenarios) if s.get("scenario_name") == GLOBAL_EQUITY_CRASH), None)
        if gec is None:
            missing_gec.append(_ev("get_stress_test", args, f"scenarios[scenario_name={GLOBAL_EQUITY_CRASH}]",
                                   None, GLOBAL_EQUITY_CRASH, None,
                                   "scenario a shock assente: composizione per classe non leggibile"))
            continue
        vector: dict[str, float] = {}
        for row in _rows(gec):
            cls = str(row.get("asset_class"))
            vector[cls] = vector.get(cls, 0.0) + (_num(row.get("weight_pct")) or 0.0)
        eligible.append({"pid": pid, "args": args, "impacts": computed, "vector": vector})

    if missing_gec:
        return _fail("Uno scenario storico è calcolato ma manca lo scenario «Global Equity Crash» "
                     "con la composizione per classe.", missing_gec)
    if len(eligible) < 2:
        return _skip("not_applicable", "Meno di due portafogli con scenari storici calcolati: "
                     "nessun confronto possibile.")

    violations: list[dict[str, Any]] = []
    pairs_checked = 0
    for i, p in enumerate(eligible):
        for q in eligible[i + 1:]:
            classes = set(p["vector"]) | set(q["vector"])
            distance = sum(abs(p["vector"].get(c, 0.0) - q["vector"].get(c, 0.0)) for c in classes)
            if distance <= COMPOSITION_L1_PP + EPS:
                continue
            common = sorted(
                name for name in set(p["impacts"]) & set(q["impacts"])
                if p["impacts"][name] is not None and q["impacts"][name] is not None
            )
            if not common:
                continue
            pairs_checked += 1
            identical = all(
                abs(p["impacts"][n] - q["impacts"][n]) <= T_EQUAL_IMPACT + EPS for n in common
            )
            if not identical:
                continue
            for name in common:
                note = (f"uguale al portafoglio {q['pid']} ({q['impacts'][name]}) pur con composizione "
                        f"per classe diversa (distanza L1 {round(distance, 2)} pp)")
                violations.append(_ev("get_stress_test", p["args"],
                                      f"scenarios[scenario_name={name}].estimated_portfolio_impact_pct",
                                      p["impacts"][name], None, T_EQUAL_IMPACT, note))
                violations.append(_ev("get_stress_test", q["args"],
                                      f"scenarios[scenario_name={name}].estimated_portfolio_impact_pct",
                                      q["impacts"][name], None, T_EQUAL_IMPACT,
                                      f"uguale al portafoglio {p['pid']}"))
    if violations:
        return _fail("Portafogli con composizione diversa hanno gli stessi impatti in tutti gli "
                     "scenari storici.", violations)
    if pairs_checked == 0:
        return _skip("not_applicable", "Nessuna coppia di portafogli con composizione per classe "
                     "diversa da confrontare.")
    return _pass([_ev("get_stress_test", e["args"], "scenarios[scenario_type=historical]"
                      ".estimated_portfolio_impact_pct", e["impacts"], None, T_EQUAL_IMPACT,
                      f"{pairs_checked} coppie confrontate") for e in eligible])


# --- A-STRESS-PROXY-TABLE ---------------------------------------------------


def check_stress_proxy_table(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    tool, args = _stress_call(scope)
    scenarios = _scenarios(ctx.scoped("get_stress_test", scope))
    if not scenarios:
        return _skip("empty_portfolio", EMPTY_REASON)
    historical = _historical(scenarios)
    # Uno scenario senza ``method`` (output precedente a TASK-38) è calcolato: va verificato.
    evaluated = [s for s in historical if s.get("method") != "not_available"]
    if not evaluated:
        return _skip("scenario_not_available", "Nessuno scenario storico calcolato (tutti not_available).")

    violations: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    for scenario in evaluated:
        definition = HISTORICAL_BY_NAME.get(scenario.get("scenario_name"))
        if definition is None:
            violations.append(_unknown_name_evidence(tool, args, scenario, HISTORICAL_BY_NAME,
                                                     "HISTORICAL_SCENARIOS"))
            continue
        proxies = HISTORICAL_CLASS_PROXIES[definition["id"]]
        method = scenario.get("method")
        rows = _rows(scenario)
        if not rows:
            violations.append(_ev(tool, args, _spath(scenario, "class_breakdown"),
                                  scenario.get("class_breakdown"), "lista non vuota", None,
                                  f"scenario storico con method {method!r} senza class_breakdown"))
            continue
        for row in rows:
            cls = row.get("asset_class")
            source = row.get("source")
            rpath = _spath(scenario, f"class_breakdown[asset_class={cls}]")
            if method == "proxy" and source != "proxy":
                violations.append(_ev(tool, args, f"{rpath}.source", source, "proxy", None,
                                      "con method proxy tutte le righe usano il proxy di classe"))
            if source != "proxy":
                continue
            value = proxies.get(cls) if isinstance(cls, str) else None
            expected = float(value if value is not None else proxies["equity"])
            observed = row.get("drawdown_pct")
            item = _ev(tool, args, f"{rpath}.drawdown_pct", observed, expected, T_PP,
                       f"HISTORICAL_CLASS_PROXIES[{definition['id']}]"
                       + ("" if value is not None else " (proxy equity)"))
            (checked if _close(observed, expected, T_PP) else violations).append(item)
    if violations:
        return _fail("Una stima storica non usa i proxy approvati per classe di attivo.", violations)
    if not checked:
        return _pass([_ev(tool, args, "scenarios[scenario_type=historical].class_breakdown[*].source",
                          "historical", None, None, "nessuna riga stimata con proxy")])
    return _pass(checked)


# --- A-STRESS-METHOD-COVERAGE -----------------------------------------------


def check_stress_method_coverage(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    tool, args = _stress_call(scope)
    scenarios = _scenarios(ctx.scoped("get_stress_test", scope))
    if not scenarios:
        return _skip("empty_portfolio", EMPTY_REASON)
    historical = _historical(scenarios)
    if not historical:
        return _skip("not_applicable", "L'output non contiene scenari storici.")

    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    threshold = HISTORICAL_MIN_COVERAGE_PCT
    for scenario in historical:
        if scenario.get("scenario_name") not in HISTORICAL_BY_NAME:
            violations.append(_unknown_name_evidence(tool, args, scenario, HISTORICAL_BY_NAME,
                                                     "HISTORICAL_SCENARIOS"))
            continue
        method = scenario.get("method")
        coverage_raw = scenario.get("coverage_pct")
        coverage = _num(coverage_raw)
        before = len(violations)
        if method not in ("historical", "proxy", "not_available"):
            violations.append(_ev(tool, args, _spath(scenario, "method"), method,
                                  ["historical", "proxy", "not_available"], None, "metodo non dichiarato"))
        elif method == "historical" and not (coverage is not None and coverage >= threshold):
            violations.append(_ev(tool, args, _spath(scenario, "coverage_pct"), coverage_raw,
                                  f">= {threshold}", None, "method historical richiede copertura >= 60%"))
        elif method == "proxy" and not (coverage is not None and coverage < threshold):
            violations.append(_ev(tool, args, _spath(scenario, "coverage_pct"), coverage_raw,
                                  f"< {threshold}", None, "method proxy richiede copertura < 60%"))
        elif method == "not_available" and coverage_raw is not None:
            violations.append(_ev(tool, args, _spath(scenario, "coverage_pct"), coverage_raw,
                                  None, None, "method not_available richiede coverage_pct null"))
        if method != "not_available" and coverage_raw is None:
            if len(violations) == before:
                violations.append(_ev(tool, args, _spath(scenario, "coverage_pct"), None,
                                      "numero", None, "coverage_pct null ma scenario calcolato"))
        if method == "proxy" and CLASS_PROXY_FLAG not in _flags(scenario):
            violations.append(_ev(tool, args, _spath(scenario, "flags"), _flags(scenario),
                                  CLASS_PROXY_FLAG, None, "flag del metodo proxy assente"))
        if any(r.get("source") == "proxy" for r in _rows(scenario)):
            note = scenario.get("methodology_note")
            if not (isinstance(note, str) and note.strip()):
                violations.append(_ev(tool, args, _spath(scenario, "methodology_note"), note,
                                      "nota non vuota", None,
                                      "righe stimate con proxy USD senza nota metodologica"))
        if len(violations) == before:
            passed.append(_ev(tool, args, _spath(scenario, "method"), method, method, None,
                              f"coverage_pct {coverage_raw}"))
    if violations:
        return _fail("Uno scenario storico non dichiara in modo coerente metodo e copertura dei "
                     "prezzi reali.", violations)
    return _pass(passed)


# --- A-STRESS-CONTRIB-SUM ---------------------------------------------------


def check_stress_contrib_sum(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    tool, args = _stress_call(scope)
    scenarios = _scenarios(ctx.scoped("get_stress_test", scope))
    if not scenarios:
        return _skip("empty_portfolio", EMPTY_REASON)

    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    evaluated = 0
    for scenario in scenarios:
        rows = _rows(scenario)
        if not rows:
            continue
        evaluated += 1
        total = sum(_num(r.get("contribution_pct")) or 0.0 for r in rows)
        impact = scenario.get("estimated_portfolio_impact_pct")
        tolerance = T_sum_pp(len(rows))
        item = _ev(tool, args, _spath(scenario, "class_breakdown[*].contribution_pct"),
                   round(total, 4), impact, tolerance,
                   "somma dei contributi contro estimated_portfolio_impact_pct")
        impact_num = _num(impact)
        (passed if impact_num is not None and abs(total - impact_num) <= tolerance + EPS
         else violations).append(item)

        if scenario.get("scenario_type") != "shock":
            continue
        for row in rows:
            cls = row.get("asset_class")
            if cls in ("equity", "unknown"):
                continue
            weight, shock, contribution = (_num(row.get(k)) for k in ("weight_pct", "shock_pct", "contribution_pct"))
            rpath = _spath(scenario, f"class_breakdown[asset_class={cls}].contribution_pct")
            expected = round(weight * shock / 100.0, 4) if weight is not None and shock is not None else None
            item = _ev(tool, args, rpath, row.get("contribution_pct"), expected, T_PP2,
                       "weight_pct × shock_pct / 100 (classe senza moltiplicatore)")
            ok = expected is not None and contribution is not None and abs(contribution - expected) <= T_PP2 + EPS
            (passed if ok else violations).append(item)
    if violations:
        return _fail("Nello stress test i contributi delle classi non tornano con l'impatto o con "
                     "peso × shock.", violations)
    if evaluated == 0:
        return _skip("not_applicable", "Nessuno scenario con class_breakdown da verificare.")
    return _pass(passed)


# --- A-STRESS-SHOCK-TABLE ---------------------------------------------------


def check_stress_shock_table(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    tool, args = _stress_call(scope)
    scenarios = _scenarios(ctx.scoped("get_stress_test", scope))
    if not scenarios:
        return _skip("empty_portfolio", EMPTY_REASON)

    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for scenario in _shock(scenarios):
        definition = SHOCK_BY_NAME.get(scenario.get("scenario_name"))
        if definition is None:
            violations.append(_unknown_name_evidence(tool, args, scenario, SHOCK_BY_NAME, "SHOCK_SCENARIOS"))
            continue
        shocks = definition["shocks"]
        note = f"tabella SHOCK_SCENARIOS, scenario {definition['id']}"
        for row in _rows(scenario):
            cls = row.get("asset_class")
            rpath = _spath(scenario, f"class_breakdown[asset_class={cls}].shock_pct")
            observed = row.get("shock_pct")
            if isinstance(cls, str) and cls in shocks:
                expected = round(shocks[cls] * 100.0, 4)
                item = _ev(tool, args, rpath, observed, expected, T_PP, note)
                (passed if _close(observed, expected, T_PP) else violations).append(item)
            elif cls == "unknown":
                expected = round(shocks["equity"] * 100.0, 4)
                item = _ev(tool, args, rpath, observed, expected, T_PP, note + " (unknown → shock equity)")
                (passed if _close(observed, expected, T_PP) else violations).append(item)
                if UNKNOWN_SHOCK_FLAG not in _flags(scenario):
                    violations.append(_ev(tool, args, _spath(scenario, "flags"), _flags(scenario),
                                          UNKNOWN_SHOCK_FLAG, None,
                                          "classe unknown con shock equity senza flag"))
            else:
                violations.append(_ev(tool, args, _spath(scenario, f"class_breakdown[asset_class={cls}]"
                                                         ".asset_class"),
                                      cls, sorted(shocks) + ["unknown"], None, "classe non ammessa"))
    if violations:
        return _fail("Lo stress test non applica a una classe di attivo lo shock della tabella approvata.",
                     violations)
    if not passed:
        return _skip("not_applicable", "Nessuna riga class_breakdown negli scenari a shock.")
    return _pass(passed)


# --- A-STRESS-NONEQUITY-POSITION-SHOCK --------------------------------------


def check_stress_nonequity_position_shock(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    tool, args = _stress_call(scope)
    scenarios = _scenarios(ctx.scoped("get_stress_test", scope))
    if not scenarios:
        return _skip("empty_portfolio", EMPTY_REASON)

    violations: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    entries_seen = 0
    for scenario in scenarios:
        entries = scenario.get("most_impacted")
        entries = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
        if not entries:
            continue
        entries_seen += len(entries)
        definition = None
        if scenario.get("scenario_type") == "shock":
            definition = SHOCK_BY_NAME.get(scenario.get("scenario_name"))
            if definition is None:
                violations.append(_unknown_name_evidence(tool, args, scenario, SHOCK_BY_NAME,
                                                         "SHOCK_SCENARIOS"))
                continue
        for entry in entries:
            symbol = entry.get("symbol")
            cls = entry.get("asset_class")
            epath = _spath(scenario, f"most_impacted[symbol={symbol}].loss_pct")
            loss_raw = entry.get("loss_pct")
            loss = _num(loss_raw)
            if loss is None or loss >= 0:
                violations.append(_ev(tool, args, epath, loss_raw, "< 0", None,
                                      "most_impacted deve elencare solo perdite reali"))
                continue
            if definition is None:
                passed.append(_ev(tool, args, epath, loss_raw, "< 0", None, None))
                continue
            shocks = definition["shocks"]
            note = f"tabella SHOCK_SCENARIOS, scenario {definition['id']}, classe {cls}"
            if cls == "equity":
                base = round(shocks["equity"] * 100.0, 4)
                allowed = [base]
                multiplier = definition.get("tech_multiplier")
                if multiplier:
                    allowed.append(round(base * float(multiplier), 4))
                ok = any(abs(loss - a) <= T_PP + EPS for a in allowed)
                (passed if ok else violations).append(_ev(tool, args, epath, loss_raw, allowed, T_PP, note))
            elif cls == "unknown" or cls is None:
                passed.append(_ev(tool, args, epath, loss_raw, "< 0", None,
                                  "classe non dichiarata o unknown: solo segno verificato"))
            elif cls in shocks:
                expected = round(shocks[cls] * 100.0, 4)
                (passed if abs(loss - expected) <= T_PP + EPS else violations).append(
                    _ev(tool, args, epath, loss_raw, expected, T_PP, note))
            else:
                violations.append(_ev(tool, args, _spath(scenario, f"most_impacted[symbol={symbol}].asset_class"),
                                      cls, sorted(shocks) + ["unknown"], None, "classe non ammessa"))
    if entries_seen == 0:
        return _skip("not_applicable", "Nessuna voce most_impacted in nessuno scenario.")
    if violations:
        return _fail("Una posizione riceve nello stress test una perdita diversa dallo shock della sua "
                     "classe (o una perdita nulla).", violations)
    return _pass(passed)


# --- Classificazione: supporto ----------------------------------------------


def _asset_info(ctx: Any, scope: Mapping[str, Any], symbol: str) -> tuple[dict[str, Any], dict[str, Any]]:
    args = {"portfolio_id": scope["portfolio_id"], "symbol": symbol}
    return ctx.scoped("search_asset_info", scope, {"symbol": symbol}), args


def _word_regex(words: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)


PRECIOUS_METAL_WORDS = _word_regex((
    "gold", "oro", "silver", "argento", "platinum", "platino", "palladium", "palladio", "precious",
))
FUND_WORDS = _word_regex(("ETF", "UCITS", "ETC", "ETN", "FUND", "FONDO", "SICAV"))


# --- A-CLASS-STRESS-CONSISTENT ----------------------------------------------


def check_class_stress_consistent(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    pid = scope["portfolio_id"]
    pos_args = {"portfolio_id": pid}
    positions = ctx.scoped("get_positions", scope).get("positions") or []
    if not positions:
        return _skip("empty_portfolio", "Portafoglio senza posizioni.")
    if len(positions) >= 30:
        return _skip("truncated_output", "get_positions restituisce 30 righe: i pesi per classe non "
                     "sono verificabili su tutte le posizioni.",
                     [_ev("get_positions", pos_args, "positions", len(positions), None, None,
                          "output limitato a 30 righe")])

    violations: list[dict[str, Any]] = []
    card_weight: dict[str, float] = {}
    card_count: dict[str, int] = {}
    card_symbols: dict[str, list[str]] = {}
    for row in positions:
        symbol = row.get("symbol")
        info, info_args = _asset_info(ctx, scope, symbol)
        cls = info.get("asset_class")
        if not isinstance(cls, str) or not cls:
            violations.append(_ev("search_asset_info", info_args, "asset_class", cls, "classe dichiarata",
                                  None, info.get("error") or "scheda senza asset_class"))
            continue
        card_weight[cls] = card_weight.get(cls, 0.0) + (_num(row.get("weight")) or 0.0)
        card_count[cls] = card_count.get(cls, 0) + 1
        card_symbols.setdefault(cls, []).append(symbol)

    stress_args = {"portfolio_id": pid}
    scenarios = _scenarios(ctx.scoped("get_stress_test", scope))
    gec = next((s for s in _shock(scenarios) if s.get("scenario_name") == GLOBAL_EQUITY_CRASH), None)
    if gec is None:
        violations.append(_ev("get_stress_test", stress_args, f"scenarios[scenario_name={GLOBAL_EQUITY_CRASH}]",
                              None, GLOBAL_EQUITY_CRASH, None, "scenario assente per un portafoglio con posizioni"))
        return _fail("Lo stress test non riporta la composizione per classe dello scenario «Global "
                     "Equity Crash».", violations)
    stress_weight: dict[str, float] = {}
    for r in _rows(gec):
        cls = str(r.get("asset_class"))
        stress_weight[cls] = stress_weight.get(cls, 0.0) + (_num(r.get("weight_pct")) or 0.0)

    passed: list[dict[str, Any]] = []
    for cls in sorted(set(card_weight) | set(stress_weight)):
        tolerance = T_sum_pp(max(card_count.get(cls, 0), 1))
        card = round(card_weight[cls], 4) if cls in card_weight else None
        stress = round(stress_weight[cls], 4) if cls in stress_weight else None
        stress_ev = _ev("get_stress_test", stress_args,
                        f"scenarios[scenario_name={GLOBAL_EQUITY_CRASH}].class_breakdown[asset_class={cls}]"
                        ".weight_pct", stress, card, tolerance,
                        "peso atteso = Σ weight di get_positions per asset_class di search_asset_info")
        card_ev = _ev("get_positions", pos_args, f"positions[*].weight (asset_class={cls})", card, None, None,
                      "somma; simboli: " + ", ".join(str(s) for s in card_symbols.get(cls, [])) if card_symbols.get(cls)
                      else "nessuna posizione con questa classe nella scheda")
        if card is None or stress is None or abs(card - stress) > tolerance + EPS:
            violations.extend([stress_ev, card_ev])
        else:
            passed.append(stress_ev)
    if violations:
        return _fail("Lo stress test classifica alcuni strumenti diversamente dalla scheda dello strumento.",
                     violations)
    return _pass(passed)


# --- A-CLASS-ETC-NOT-EQUITY -------------------------------------------------


def check_class_etc_not_equity(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    info, args = _asset_info(ctx, scope, scope["symbol"])
    itype = info.get("instrument_type")
    if itype not in ("etc", "etn"):
        return _skip("not_applicable", "Lo strumento non è un ETC o un ETN.",
                     [_ev("search_asset_info", args, "instrument_type", itype, ["etc", "etn"], None, None)])
    cls = info.get("asset_class")
    name = info.get("name") if isinstance(info.get("name"), str) else ""
    violations: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    if itype == "etc":
        item = _ev("search_asset_info", args, "asset_class", cls, ["gold", "commodity"], None,
                   f"instrument_type etc, nome {name!r}")
        (evidence if cls in ("gold", "commodity") else violations).append(item)
    match = PRECIOUS_METAL_WORDS.search(name)
    if match:
        item = _ev("search_asset_info", args, "asset_class", cls, "diversa da equity", None,
                   f"{itype} su metalli preziosi (parola «{match.group(0)}» nel nome)")
        (evidence if cls != "equity" else violations).append(item)
    if violations:
        return _fail(f"Un {itype.upper()} su metalli preziosi o materie prime è classificato come «{cls}».",
                     violations)
    if not evidence:
        evidence.append(_ev("search_asset_info", args, "asset_class", cls, None, None,
                            "ETN senza metalli preziosi nel nome: nessun vincolo di classe"))
    return _pass(evidence)


# --- A-CLASS-ETP-TER-NONZERO ------------------------------------------------


def check_class_etp_ter_nonzero(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    symbol = scope["symbol"]
    info, args = _asset_info(ctx, scope, symbol)
    itype = info.get("instrument_type")
    if itype not in ("etc", "etn", "etf", "fund"):
        return _skip("not_applicable", "Lo strumento non è un ETF, ETC, ETN o fondo.",
                     [_ev("search_asset_info", args, "instrument_type", itype,
                          ["etc", "etn", "etf", "fund"], None, None)])
    cost_args = {"portfolio_id": scope["portfolio_id"]}
    costs = ctx.scoped("get_cost_breakdown", scope)
    rows = costs.get("position_costs") if isinstance(costs.get("position_costs"), list) else []
    row = next((r for r in rows if isinstance(r, dict) and r.get("symbol") == symbol), None)
    if row is None:
        return _skip("truncated_output", "Lo strumento non compare fra le righe di position_costs "
                     "(al più 20).", [_ev("get_cost_breakdown", cost_args, f"position_costs[symbol={symbol}]",
                                          None, None, None, f"{len(rows)} righe")])
    path = f"position_costs[symbol={symbol}]"
    ter = row.get("ter_pct")
    source = row.get("ter_source")
    evidence = [
        _ev("search_asset_info", args, "instrument_type", itype, ["etc", "etn", "etf", "fund"], None, None),
        _ev("get_cost_breakdown", cost_args, f"{path}.ter_pct", ter, "diverso da 0 se dedotto", None,
            f"ter_source {source!r}"),
    ]
    if source == "inferred" and _num(ter) == 0:
        return _fail(f"Il {itype.upper()} {symbol} risulta a costo zero per un TER dedotto.", evidence)
    return _pass(evidence)


# --- A-CLASS-BOND-TYPE ------------------------------------------------------


def check_class_bond_type(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    info, args = _asset_info(ctx, scope, scope["symbol"])
    stored_type = info.get("type")
    if stored_type != "bond":
        return _skip("not_applicable", "Lo strumento non è registrato come obbligazione.",
                     [_ev("search_asset_info", args, "type", stored_type, "bond", None, None)])
    name = info.get("name") if isinstance(info.get("name"), str) else ""
    words = sorted({m.group(0).upper() for m in FUND_WORDS.finditer(name)})
    evidence = [_ev("search_asset_info", args, "name", name, "nome senza ETF/UCITS/ETC/ETN/FUND/FONDO/SICAV",
                    None, f"type bond; parole trovate: {', '.join(words)}" if words else "type bond")]
    if words:
        return _fail("Un fondo o un ETP è registrato come singola obbligazione (type bond).", evidence)
    return _pass(evidence)


# --- A-CLASS-UNKNOWN-DECLARED -----------------------------------------------


def check_class_unknown_declared(ctx: Any, scope: dict[str, Any]) -> dict[str, Any]:
    info, args = _asset_info(ctx, scope, scope["symbol"])
    cls = info.get("asset_class")
    if cls != "unknown":
        return _skip("not_applicable", "Lo strumento ha una classe di attivo riconosciuta.",
                     [_ev("search_asset_info", args, "asset_class", cls, "unknown", None, None)])
    stress_args = {"portfolio_id": scope["portfolio_id"]}
    scenarios = _scenarios(ctx.scoped("get_stress_test", scope))
    if not scenarios:
        return _skip("empty_portfolio", EMPTY_REASON)
    shock = _shock(scenarios)
    if not shock:
        return _skip("not_applicable", "Nessuno scenario a shock nell'output dello stress test.")
    violations: list[dict[str, Any]] = []
    passed = [_ev("search_asset_info", args, "asset_class", cls, "unknown", None, None)]
    for scenario in shock:
        flags = _flags(scenario)
        item = _ev("get_stress_test", stress_args, _spath(scenario, "flags"), flags, UNKNOWN_SHOCK_FLAG, None,
                   f"strumento {scope['symbol']} non classificabile")
        (passed if UNKNOWN_SHOCK_FLAG in flags else violations).append(item)
        classes = [r.get("asset_class") for r in _rows(scenario)]
        item = _ev("get_stress_test", stress_args, _spath(scenario, "class_breakdown[*].asset_class"),
                   classes, "contiene unknown", None, None)
        (passed if "unknown" in classes else violations).append(item)
    if violations:
        return _fail("Uno strumento non classificabile è trattato come azione senza dichiararlo.", violations)
    return _pass(passed)


# --- Dichiarazioni (rules.md §2) --------------------------------------------

_STRESS_TOOLS = ["get_stress_test", "get_aggregate_stress_test"]

RULES: list[dict[str, Any]] = [
    {
        "id": "A-STRESS-HIST-DISTINCT",
        "group": "A",
        "title": "Gli scenari storici danno risultati diversi per portafogli con composizione diversa",
        "area": "stress",
        "severity": "P0",
        "findings": ["V365-001"],
        "scopes": ["user"],
        "tools": ["get_stress_test"],
        "check": check_stress_hist_distinct,
        "timeout_s": 60.0,
    },
    {
        "id": "A-STRESS-PROXY-TABLE",
        "group": "A",
        "title": "Le stime storiche senza prezzi usano i valori approvati per ogni classe di attivo",
        "area": "stress",
        "severity": "P0",
        "findings": ["V365-001"],
        "scopes": ["portfolio", "aggregate"],
        "tools": list(_STRESS_TOOLS),
        "check": check_stress_proxy_table,
    },
    {
        "id": "A-STRESS-METHOD-COVERAGE",
        "group": "A",
        "title": "Ogni scenario storico dichiara metodo e copertura dei prezzi reali",
        "area": "stress",
        "severity": "P1",
        "findings": ["V365-001"],
        "scopes": ["portfolio", "aggregate"],
        "tools": list(_STRESS_TOOLS),
        "check": check_stress_method_coverage,
    },
    {
        "id": "A-STRESS-CONTRIB-SUM",
        "group": "A",
        "title": "Nello stress test i contributi delle classi sommano all'impatto totale",
        "area": "stress",
        "severity": "P1",
        "findings": ["V365-001", "V365-002"],
        "scopes": ["portfolio", "aggregate"],
        "tools": list(_STRESS_TOOLS),
        "check": check_stress_contrib_sum,
    },
    {
        "id": "A-STRESS-SHOCK-TABLE",
        "group": "A",
        "title": "Lo stress test applica a ogni classe di attivo lo shock previsto",
        "area": "stress",
        "severity": "P0",
        "findings": ["V365-002"],
        "scopes": ["portfolio", "aggregate"],
        "tools": list(_STRESS_TOOLS),
        "check": check_stress_shock_table,
    },
    {
        "id": "A-STRESS-NONEQUITY-POSITION-SHOCK",
        "group": "A",
        "title": "Obbligazioni, oro e materie prime non ricevono lo shock delle azioni",
        "area": "stress",
        "severity": "P0",
        "findings": ["V365-002"],
        "scopes": ["portfolio", "aggregate"],
        "tools": list(_STRESS_TOOLS),
        "check": check_stress_nonequity_position_shock,
    },
    {
        "id": "A-CLASS-STRESS-CONSISTENT",
        "group": "A",
        "title": "Lo stress test classifica gli strumenti come la scheda dello strumento",
        "area": "classification",
        "severity": "P0",
        "findings": ["V365-002", "V365-012"],
        "scopes": ["portfolio"],
        "tools": ["get_positions", "search_asset_info", "get_stress_test"],
        "check": check_class_stress_consistent,
    },
    {
        "id": "A-CLASS-ETC-NOT-EQUITY",
        "group": "A",
        "title": "Gli ETC su oro e metalli preziosi non sono classificati come azioni",
        "area": "classification",
        "severity": "P1",
        "findings": ["V365-012"],
        "scopes": ["instrument"],
        "tools": ["search_asset_info"],
        "check": check_class_etc_not_equity,
    },
    {
        "id": "A-CLASS-ETP-TER-NONZERO",
        "group": "A",
        "title": "ETF ed ETC non risultano a costo zero per un TER dedotto",
        "area": "classification",
        "severity": "P2",
        "findings": ["V365-012", "V365-007"],
        "scopes": ["instrument"],
        "tools": ["search_asset_info", "get_cost_breakdown"],
        "check": check_class_etp_ter_nonzero,
    },
    {
        "id": "A-CLASS-BOND-TYPE",
        "group": "A",
        "title": "Un fondo obbligazionario non è registrato come singola obbligazione",
        "area": "classification",
        "severity": "P2",
        "findings": ["V-BOND-QUOTETYPE"],
        "scopes": ["instrument"],
        "tools": ["search_asset_info"],
        "check": check_class_bond_type,
    },
    {
        "id": "A-CLASS-UNKNOWN-DECLARED",
        "group": "A",
        "title": "Gli strumenti non classificabili sono dichiarati, non trattati in silenzio come azioni",
        "area": "classification",
        "severity": "P2",
        "findings": ["V365-002"],
        "scopes": ["instrument"],
        "tools": ["search_asset_info", "get_stress_test"],
        "check": check_class_unknown_declared,
    },
]
