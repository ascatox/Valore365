"""Fascicolo dei fatti del Tribunale (docs/tribunale/api-contracts.md §4).

Dato uno scope (un portafoglio o una vista aggregata) raccoglie i dati già
calcolati dal Doctor in un elenco di fatti con id stabili (``F1``…), valore
formattato in italiano, fonte e qualità del dato. Il fascicolo è l'unica fonte
di numeri della seduta: quello che non c'è non può essere detto.

Nessun LLM, nessun calcolo duplicato: si riusano ``DoctorPolicyService``
(scope, snapshot, metriche del registry, evaluation della policy),
``canonical_securities``, ``format_it`` e i servizi del Portfolio Doctor
(health, X-Ray, stress test, Monte Carlo). Un dato mancante, stale o UNKNOWN
diventa un fatto non citabile con il motivo, mai uno zero.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Callable, Iterable, Mapping
from contextlib import nullcontext
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ...constants.stress_scenarios import HISTORICAL_SCENARIOS
from ..doctor_policy.metrics import (
    METHODOLOGY_VERSION,
    METRIC_CODES,
    METRIC_REGISTRY,
    MetricValue,
    canonical_securities,
    format_it,
    format_threshold_it,
)
from ..doctor_policy.scope import build_scope
from ..portfolio_doctor import (
    analyze_portfolio_health,
    compute_portfolio_xray,
    run_monte_carlo_projection,
    run_stress_test,
)
from ..portfolio_doctor._xray import UNCLASSIFIED_LABEL

if TYPE_CHECKING:  # pragma: no cover
    from ..doctor_policy.service import DoctorPolicyService

logger = logging.getLogger("valore365.tribunal")

CONTRACT_VERSION: str = "tribunale-1.0"
CASE_FILE_SCHEMA_VERSION: int = 1
MAX_FACTS: int = 40
MIN_CITABLE_FACTS: int = 6
MAX_INSTRUMENTS: int = 30
# ``value`` escluso di proposito: l'hash segue ciò che l'utente vede (``formatted``),
# così un aggiornamento di prezzo che non cambia nessun valore formattato non cambia
# l'hash e la seduta salvata si riusa (api-contracts §4.6, TASK-66).
HASH_FACT_FIELDS: tuple[str, ...] = (
    "id", "key", "group", "label", "unit", "formatted", "source",
    "quality", "citable", "reason", "subject", "sensitive",
)

# Limiti di lunghezza dello schema (api-contracts §4.1, §4.7).
MAX_LABEL_CHARS = 160
MAX_REASON_CHARS = 300
MAX_SUBJECT_CHARS = 80
MAX_KEY_CHARS = 120
MAX_FORMATTED_CHARS = 40
MAX_SYMBOL_CHARS = 20
INSTRUMENT_NAME_CHARS = 60  # clean_text(name, max_chars=60): ≤ 61 con «…»

MAX_ALERTS = 3
MAX_XRAY_ROWS = 3
MAX_POLICY_RULES = 4
MIN_PARTIAL_COVERAGE_PCT = 80.0
MC_YEARS = (10, 20)
MC_PERCENTILES = (("p10", "10° percentile"), ("p50", "mediana"), ("p90", "90° percentile"))

STALE_NOTE_PREFIX = "Quotazioni non aggiornate"
PROXY_DEFAULT_REASON = "Stima con proxy di classe: prezzi reali su meno del 60% del peso nel periodo."
RECOVERY_MISSING_REASON = "Tempo di recupero non disponibile per questo scenario."
SCENARIO_MISSING_REASON = "Scenario non calcolabile per questo portafoglio."
MC_MISSING_REASON = "Proiezione Monte Carlo non disponibile: storico dei prezzi insufficiente."
VOLATILITY_MISSING_REASON = "Volatilità non calcolabile: storico dei prezzi insufficiente."

ALERT_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
ALERT_SEVERITY_TEXT = {"critical": "critico", "warning": "attenzione", "info": "informativo"}

# Gruppo -> ordine nel catalogo (api-contracts §4.3), per il taglio a MAX_FACTS.
GROUP_ORDER = (
    "composizione", "concentrazione", "costi", "salute", "esposizione", "stress", "scenari", "regole",
)
# Righe a numero variabile (si tolgono per prime se si supera MAX_FACTS).
VARIABLE_KEY_PREFIXES = ("health.alert.", "xray.country.", "xray.sector.", "policy.rule.")
# Mai tolti: le 8 metriche del registry e il punteggio di salute.
PROTECTED_KEY_PREFIXES = ("metric.",)
PROTECTED_KEYS = frozenset({"health.score"})

# Metriche del registry: (code, group), nell'ordine del catalogo.
METRIC_ROWS: tuple[tuple[str, str], ...] = (
    ("equity_weight_pct", "composizione"),
    ("bond_weight_pct", "composizione"),
    ("gold_weight_pct", "composizione"),
    ("usa_exposure_pct", "composizione"),
    ("max_single_position_pct", "concentrazione"),
    ("top3_positions_pct", "concentrazione"),
    ("etf_overlap_pct", "concentrazione"),
)
TER_CODE = "weighted_ter_pct"


# ---------------------------------------------------------------------------
# Formattazione e pulizia
# ---------------------------------------------------------------------------


def _clean_text(value: str, *, max_chars: int) -> str:
    from ...copilot_doctor_tools import clean_text  # import locale: evita cicli

    return clean_text(value, max_chars=max_chars)


def _clean(value: Any, limit: int) -> str:
    """Testo su una riga, caratteri di controllo/bidi rimossi, ≤ ``limit``."""
    text = " ".join(str(value).split())
    return _clean_text(text, max_chars=max(1, limit - 1))


def _clean_opt(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = _clean(value, limit)
    return text or None


def _round_value(value: Any) -> float | None:
    """``round(x, 4)``, ``-0.0`` -> ``0.0``; non numerico/non finito -> None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    rounded = round(number, 4)
    return 0.0 if rounded == 0 else rounded


def _int_value(value: Any) -> int | None:
    rounded = _round_value(value)
    return None if rounded is None else int(round(rounded))


def format_fact_value(value: float | int | str | None, unit: str, *, decimals: int = 1) -> str:
    """Valore formattato in italiano (api-contracts §4.5)."""
    if value is None:
        return "N/D"
    if unit == "text":
        return str(value)
    number = float(value)
    if unit == "pct":
        return format_it(number, decimals) + "%"
    if unit == "score":
        return f"{int(number)}/100"
    if unit == "count":
        return f"{int(number):,}".replace(",", ".")
    if unit == "index":
        return format_it(number, 1)
    if unit == "months":
        months = int(number)
        return "1 mese" if months == 1 else f"{months} mesi"
    raise ValueError(f"Unità non valida: {unit!r}")


# ---------------------------------------------------------------------------
# Costruzione dei fatti
# ---------------------------------------------------------------------------


def _fact(
    key: str, group: str, label: str, value: Any, unit: str, source: str, *,
    quality: str = "ok", citable: bool = True, reason: str | None = None,
    subject: str | None = None, decimals: int = 1,
) -> dict[str, Any]:
    if unit in ("pct", "index"):
        value = _round_value(value)
    elif unit in ("count", "score", "months"):
        value = _int_value(value)
    elif unit == "text":
        value = None if value is None else _clean(value, MAX_FORMATTED_CHARS)
    if value is None:
        # Un dato mancante non è mai zero e non è mai citabile.
        quality, citable = "missing", False
        reason = reason or "Dato non disponibile."
    if not citable and not reason:
        reason = "Dato non citabile."
    return {
        "id": "",
        "key": _clean(key, MAX_KEY_CHARS),
        "group": group,
        "label": _clean(label, MAX_LABEL_CHARS),
        "value": value,
        "unit": unit,
        "formatted": format_fact_value(value, unit, decimals=decimals),
        "source": source,
        "quality": quality,
        "citable": bool(citable),
        "reason": _clean_opt(reason, MAX_REASON_CHARS),
        "subject": _clean_opt(subject, MAX_SUBJECT_CHARS),
        "sensitive": unit == "score",
    }


def _missing(key: str, group: str, label: str, unit: str, source: str, reason: str, **kw: Any) -> dict[str, Any]:
    return _fact(key, group, label, None, unit, source, quality="missing", citable=False, reason=reason, **kw)


def _block_reason(block: str) -> str:
    return f"Dato non disponibile: {block} non calcolabile."


def _stale_note(metric: MetricValue) -> str | None:
    return next((n for n in metric.notes if str(n).startswith(STALE_NOTE_PREFIX)), None)


def _metric_fact(code: str, group: str, metric: MetricValue | None) -> dict[str, Any]:
    definition = METRIC_REGISTRY[code]
    decimals = 2 if code == TER_CODE else 1
    key, label = f"metric.{code}", definition.label
    common = {"decimals": decimals}
    if metric is None:
        return _missing(key, group, label, "pct", "doctor_metrics", "Dato non disponibile.", **common)
    if code == "max_single_position_pct" and metric.contributors:
        common["subject"] = metric.contributors[0].get("symbol")
    other_notes = [n for n in metric.notes if not str(n).startswith(STALE_NOTE_PREFIX)]
    if metric.value is None or metric.quality == "missing":
        reason = other_notes[-1] if other_notes else "Dato non disponibile."
        return _missing(key, group, label, "pct", "doctor_metrics", reason, **common)
    if metric.quality == "stale":
        reason = _stale_note(metric) or "Quotazioni non aggiornate."
        return _fact(key, group, label, metric.value, "pct", "doctor_metrics",
                     quality="stale", citable=False, reason=reason, **common)
    if metric.quality == "partial":
        coverage = metric.coverage_pct
        if coverage is None or coverage < MIN_PARTIAL_COVERAGE_PCT:
            shown = "N/D" if coverage is None else format_it(coverage, 1) + "%"
            return _fact(key, group, label, metric.value, "pct", "doctor_metrics", quality="partial",
                         citable=False, reason=f"Copertura insufficiente ({shown}).", **common)
        universe = "con TER noto" if code == TER_CODE else "classificato"
        reason = f"Stima sul {format_it(coverage, 1)}% del valore investito {universe}"
        lower, upper = metric.lower, metric.upper
        if lower is not None and upper is not None and round(lower, 4) != round(upper, 4):
            reason += (
                f"; intervallo tra {format_it(lower, decimals)}% e {format_it(upper, decimals)}%"
            )
        return _fact(key, group, label, metric.value, "pct", "doctor_metrics",
                     quality="partial", citable=True, reason=reason + ".", **common)
    return _fact(key, group, label, metric.value, "pct", "doctor_metrics", **common)


def _health_facts(health: Any, error: bool) -> list[dict[str, Any]]:
    score_label = "Punteggio di salute del Doctor"
    vol_label = "Volatilità annua stimata del portafoglio"
    if error or health is None:
        reason = _block_reason("health score")
        return [
            _missing("health.score", "salute", score_label, "score", "health_score", reason),
            _missing("health.volatility_pct", "salute", vol_label, "pct", "health_score", reason),
        ]
    facts = [
        _fact("health.score", "salute", score_label, health.score, "score", "health_score"),
        _fact("health.volatility_pct", "salute", vol_label, health.metrics.portfolio_volatility, "pct",
              "health_score", reason=None if health.metrics.portfolio_volatility is not None
              else VOLATILITY_MISSING_REASON),
    ]
    best: dict[str, Any] = {}
    for alert in health.alerts or []:
        severity = ALERT_SEVERITY_ORDER.get(alert.severity, 99)
        current = best.get(alert.type)
        if current is None or severity < ALERT_SEVERITY_ORDER.get(current.severity, 99):
            best[alert.type] = alert
    ordered = sorted(best.values(), key=lambda a: (ALERT_SEVERITY_ORDER.get(a.severity, 99), a.type))
    for alert in ordered[:MAX_ALERTS]:
        facts.append(_fact(
            f"health.alert.{alert.type}", "salute", "Avviso del Doctor: " + str(alert.message),
            ALERT_SEVERITY_TEXT.get(alert.severity, "informativo"), "text", "health_alerts",
        ))
    return facts


def _top_exposures(exposure: Mapping[str, Any] | None) -> list[tuple[str, float]]:
    rows = []
    for name, weight in (exposure or {}).items():
        value = _round_value(weight)
        if name == UNCLASSIFIED_LABEL or value is None or value <= 0:
            continue
        rows.append((str(name), value))
    rows.sort(key=lambda r: (-r[1], r[0]))
    return rows[:MAX_XRAY_ROWS]


def _xray_facts(xray: Any, error: bool) -> list[dict[str, Any]]:
    label = "Copertura del look-through X-Ray"
    if error or xray is None:
        return [_missing("xray.coverage_pct", "esposizione", label, "pct", "xray", _block_reason("X-Ray"))]
    countries = xray.aggregated_country_exposure or {}
    unclassified = _round_value(countries.get(UNCLASSIFIED_LABEL))
    reason = f"Non classificato: {format_it(unclassified, 1)}%." if unclassified else None
    facts = [_fact("xray.coverage_pct", "esposizione", label, xray.lookthrough_coverage_pct, "pct", "xray",
                   reason=reason)]
    for kind, title, exposure in (
        ("country", "paese", countries),
        ("sector", "settore", getattr(xray, "aggregated_sector_exposure", None) or {}),
    ):
        for name, value in _top_exposures(exposure):
            clean_name = _clean(name, MAX_SUBJECT_CHARS)
            facts.append(_fact(
                f"xray.{kind}.{clean_name}", "esposizione",
                f"Esposizione per {title} (parte scomposta): {clean_name}", value, "pct", "xray",
                subject=clean_name,
            ))
    return facts


def _stress_facts(stress: Any, error: bool) -> list[dict[str, Any]]:
    by_id = {}
    if not error and stress is not None:
        by_id = {s.scenario_id: s for s in stress.scenarios if s.scenario_type == "historical"}
    facts: list[dict[str, Any]] = []
    for scenario in HISTORICAL_SCENARIOS:
        sid = scenario["id"]
        result = by_id.get(sid)
        name = result.scenario_name if result is not None else scenario["name"]
        period = (result.period if result is not None else scenario.get("period")) or ""
        head = f"Stress test «{name}»" + (f" ({period})" if period else "")
        impact_label, recovery_label = f"{head}: impatto stimato", f"{head}: mesi per il recupero"
        impact_key, recovery_key = f"stress.{sid}.impact", f"stress.{sid}.recovery_months"
        if result is None or result.method == "not_available":
            reason = _block_reason("stress test") if error or stress is None else SCENARIO_MISSING_REASON
            facts.append(_missing(impact_key, "stress", impact_label, "pct", "stress_test", reason))
            facts.append(_missing(recovery_key, "stress", recovery_label, "months", "stress_test", reason))
            continue
        proxy = result.method == "proxy"
        quality = "partial" if proxy else "ok"
        reason = (result.methodology_note or PROXY_DEFAULT_REASON) if proxy else None
        facts.append(_fact(impact_key, "stress", impact_label, result.estimated_portfolio_impact_pct, "pct",
                           "stress_test", quality=quality, reason=reason))
        if result.recovery_months is None:
            facts.append(_missing(recovery_key, "stress", recovery_label, "months", "stress_test",
                                  RECOVERY_MISSING_REASON))
        else:
            facts.append(_fact(recovery_key, "stress", recovery_label, result.recovery_months, "months",
                               "stress_test", quality=quality, reason=reason))
    return facts


def _mc_facts(mc: Any, error: bool) -> list[dict[str, Any]]:
    by_year = {}
    if not error and mc is not None:
        by_year = {p.year: p for p in mc.projections}
    reason = _block_reason("Monte Carlo") if error or mc is None else MC_MISSING_REASON
    facts = []
    for year in MC_YEARS:
        projection = by_year.get(year)
        for field, text in MC_PERCENTILES:
            key = f"mc.y{year}.{field}"
            label = f"Monte Carlo a {year} anni, {text} (base 100)"
            value = getattr(projection, field, None) if projection is not None else None
            if value is None:
                facts.append(_missing(key, "scenari", label, "index", "monte_carlo", reason))
            else:
                facts.append(_fact(key, "scenari", label, value, "index", "monte_carlo"))
    return facts


def _threshold_text(result: Any) -> str:
    def pct(v: Any) -> str:
        return format_threshold_it(float(v)) + "%"

    if result.operator == "min" and result.min_value is not None:
        return f"al minimo {pct(result.min_value)}"
    if result.operator == "max" and result.max_value is not None:
        return f"al massimo {pct(result.max_value)}"
    if result.operator == "range" and result.min_value is not None and result.max_value is not None:
        return f"tra {pct(result.min_value)} e {pct(result.max_value)}"
    return ""


def _policy_facts(evaluation: Any) -> list[dict[str, Any]]:
    if evaluation is None or evaluation.status == "no_policy":
        return []
    facts = [_fact("policy.failed_count", "regole", "Regole personali violate",
                   evaluation.summary.failed, "count", "doctor_policy")]
    rules = [r for r in evaluation.results if r.status in ("FAIL", "UNKNOWN")][:MAX_POLICY_RULES]
    for rule in rules:
        definition = METRIC_REGISTRY.get(rule.metric_code)
        metric_label = definition.label if definition else rule.metric_code
        threshold = _threshold_text(rule)
        label = f"Tua regola «{rule.label or metric_label}»: {metric_label}" + (f", {threshold}" if threshold else "")
        key = f"policy.rule.{rule.rule_id}"
        if rule.status == "FAIL":
            facts.append(_fact(key, "regole", label, "violata", "text", "doctor_policy"))
        else:
            facts.append(_fact(key, "regole", label, "non verificabile", "text", "doctor_policy",
                               quality="partial", citable=False,
                               reason=rule.reason or "Regola non verificabile con i dati disponibili."))
    return facts


def _trim(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Taglio a MAX_FACTS (api-contracts §4.3): prima le righe a numero
    variabile dal fondo di ciascun blocco, dall'ultimo gruppo al primo; mai le
    metriche del registry né ``health.score``."""
    facts = list(facts)

    def removable(fact: dict[str, Any], variable_only: bool) -> bool:
        key = fact["key"]
        if key in PROTECTED_KEYS or key.startswith(PROTECTED_KEY_PREFIXES):
            return False
        return key.startswith(VARIABLE_KEY_PREFIXES) or not variable_only

    for variable_only in (True, False):
        for group in reversed(GROUP_ORDER):
            while len(facts) > MAX_FACTS:
                index = next(
                    (i for i in range(len(facts) - 1, -1, -1)
                     if facts[i]["group"] == group and removable(facts[i], variable_only)),
                    None,
                )
                if index is None:
                    break
                facts.pop(index)
    return facts


# ---------------------------------------------------------------------------
# API pubblica
# ---------------------------------------------------------------------------


def compute_case_file_hash(case_file: Mapping[str, Any]) -> str:
    """sha256 del contenuto rilevante del fascicolo (api-contracts §4.6)."""
    payload = {
        "contract_version": case_file["contract_version"],
        "schema_version": case_file["schema_version"],
        "scope_fingerprint": case_file["scope"]["fingerprint"],
        "methodology_version": case_file["methodology_version"],
        "instruments": case_file["instruments"],
        "facts": [{k: f[k] for k in HASH_FACT_FIELDS} for f in case_file["facts"]],
    }
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def facts_by_id(case_file: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["id"]: f for f in case_file.get("facts") or []}


def _instruments(snapshot: Any) -> list[dict[str, Any]]:
    groups = sorted(canonical_securities(snapshot), key=lambda g: (-g["weight_pct"], str(g["symbol"] or "")))
    out = []
    for g in groups[:MAX_INSTRUMENTS]:
        symbol = " ".join(str(g["symbol"] or "").split())
        out.append({
            "symbol": _clean_text(symbol, max_chars=MAX_SYMBOL_CHARS)[:MAX_SYMBOL_CHARS],
            "isin": _clean_opt(g.get("isin"), MAX_SYMBOL_CHARS) if g.get("isin") else None,
            "name": _clean_text(" ".join(str(g["name"] or g["symbol"] or "").split()),
                                max_chars=INSTRUMENT_NAME_CHARS),
        })
    return out


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_block(name: str, call: Callable[[], Any]) -> tuple[Any, bool]:
    """Un blocco che fallisce non fa fallire il fascicolo."""
    try:
        return call(), False
    except Exception as exc:  # noqa: BLE001 - blocco del Doctor non calcolabile
        logger.warning("tribunal.case_file block=%s error=%s", name, type(exc).__name__)
        return None, True


def build_case_file(
    repo: Any, user_id: str, portfolio_ids: Iterable[int], *,
    service: "DoctorPolicyService | None" = None,
    now: datetime | None = None,
    finance_client: Any = None,
    justetf_client: Any = None,
) -> dict[str, Any]:
    """CaseFile (api-contracts §4.2). status "empty_portfolio" con facts [] se lo scope non ha
    posizioni investite. Solleva doctor_policy.errors.InvalidRequest (400) e NotFound (404)
    come DoctorPolicyService.resolve_scope. Non chiama mai un LLM.

    ``finance_client``/``justetf_client`` sono passati a ``compute_portfolio_xray``
    come nelle route del Doctor (senza, l'X-Ray usa solo i dati già salvati).
    """
    if service is None:
        from ..doctor_policy.service import get_doctor_policy_service

        service = get_doctor_policy_service(repo)
    current = now if now is not None else datetime.now(UTC)

    ids = service.resolve_scope(portfolio_ids, user_id)  # NotFound / InvalidRequest
    scope = build_scope(ids)
    ref: int | list[int] = ids[0] if len(ids) == 1 else list(ids)

    memoize = getattr(repo, "memoize_positions", None)
    with (memoize() if callable(memoize) else nullcontext()):
        snapshot, metrics = service._snapshot_and_metrics(ids, user_id)
        notes: list[str] = []
        if scope.scope_type == "aggregate":
            notes.append(f"Vista aggregata di {len(ids)} portafogli.")
        case_file: dict[str, Any] = {
            "schema_version": CASE_FILE_SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "status": "ready",
            "scope": scope.model_dump(),
            "generated_at": _iso_utc(current),
            "as_of": snapshot.quote_as_of,
            "methodology_version": METHODOLOGY_VERSION,
            "hash": "",
            "instruments": [],
            "facts": [],
            "counts": {"total": 0, "citable": 0},
            "notes": notes,
        }
        if snapshot.is_empty:
            case_file["status"] = "empty_portfolio"
            case_file["hash"] = compute_case_file_hash(case_file)
            return case_file

        securities = canonical_securities(snapshot)
        facts: list[dict[str, Any]] = [_metric_fact(code, group, metrics.get(code)) for code, group in METRIC_ROWS]
        facts.append(_fact("positions.count", "concentrazione", "Numero di posizioni", len(securities),
                           "count", "positions"))
        facts.append(_metric_fact(TER_CODE, "costi", metrics.get(TER_CODE)))

        health, health_err = _run_block("health", lambda: analyze_portfolio_health(repo, ref, user_id))
        facts.extend(_health_facts(health, health_err))
        xray, xray_err = _run_block(
            "xray", lambda: compute_portfolio_xray(repo, ref, user_id, finance_client, justetf_client=justetf_client),
        )
        facts.extend(_xray_facts(xray, xray_err))
        stress, stress_err = _run_block("stress", lambda: run_stress_test(repo, ref, user_id))
        facts.extend(_stress_facts(stress, stress_err))
        mc, mc_err = _run_block("monte_carlo", lambda: run_monte_carlo_projection(repo, ref, user_id))
        facts.extend(_mc_facts(mc, mc_err))
        evaluation, _policy_err = _run_block("policy", lambda: service.evaluate(user_id, ids))
        facts.extend(_policy_facts(evaluation))

    facts = _trim(facts)
    for index, fact in enumerate(facts, start=1):
        fact["id"] = f"F{index}"

    stale = next((n for code in METRIC_CODES if (m := metrics.get(code)) and (n := _stale_note(m))), None)
    if stale:
        notes.append(_clean(stale, MAX_REASON_CHARS))

    case_file["instruments"] = _instruments(snapshot)
    case_file["facts"] = facts
    case_file["counts"] = {"total": len(facts), "citable": sum(1 for f in facts if f["citable"])}
    case_file["hash"] = compute_case_file_hash(case_file)
    return case_file
