"""Deterministic evaluation of a policy over the metrics of a snapshot (§4).

Statuses: PASS | FAIL | UNKNOWN | NOT_APPLICABLE | INACTIVE, plus the
``near_limit`` flag on PASS results. Values are compared unrounded with
EPSILON = 1e-9 and inclusive bounds (a value equal to the limit passes).

Order of the checks for an enabled rule:
1. stale data (a price older than ``max_data_age_days``, a price flagged
   stale, a failed price sync) -> UNKNOWN, never PASS;
2. prices missing for more than ``100 - min_coverage_pct`` of the value ->
   UNKNOWN;
3. metric not available -> UNKNOWN;
4. conservative bounds decisive (max: upper <= max PASS, lower > max FAIL;
   min symmetric; range both) -> that status, whatever the coverage;
5. only for a metric without upper bound (partial TER) and coverage >=
   ``min_coverage_pct`` -> status of the covered-universe value (quality
   ``partial``, coverage in the reason);
6. otherwise UNKNOWN: the point estimate of a partially classified metric is
   never used (PRD D04, "mai verde automatico su dati sconosciuti").

The reasons describe the user's own rule; they never say whether an
investment is suitable or advisable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ...schemas.doctor_policy import (
    DataQuality,
    EvaluationSummary,
    MetricContributor,
    MetricEvidence,
    PolicyEvaluationResponse,
    RuleResult,
)
from .metrics import METHODOLOGY_VERSION, METRIC_REGISTRY, MetricValue, compute_metrics, format_it, format_threshold_it
from .scope import build_scope
from .snapshot import DoctorSnapshot
from .validator import EPSILON, normalize_policy_document

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
PP = "punti percentuali"


@dataclass
class PolicyEvaluation:
    results: list[RuleResult]
    summary: EvaluationSummary
    calculated_at: str
    methodology_version: str = METHODOLOGY_VERSION
    snapshot_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# comparisons
# ---------------------------------------------------------------------------


def _le(a: float, b: float) -> bool:
    return a <= b + EPSILON


def _ge(a: float, b: float) -> bool:
    return a >= b - EPSILON


def _status_for_interval(rule: dict[str, Any], lower: float | None, upper: float | None) -> str | None:
    """PASS / FAIL when the interval [lower, upper] decides the rule, else None.

    A missing bound is unbounded on that side.
    """
    op = rule["operator"]
    checks = []
    if op in ("max", "range"):
        limit = rule["max_value"]
        if upper is not None and _le(upper, limit):
            checks.append("PASS")
        elif lower is not None and not _le(lower, limit):
            checks.append("FAIL")
        else:
            checks.append(None)
    if op in ("min", "range"):
        limit = rule["min_value"]
        if lower is not None and _ge(lower, limit):
            checks.append("PASS")
        elif upper is not None and not _ge(upper, limit):
            checks.append("FAIL")
        else:
            checks.append(None)
    if "FAIL" in checks:
        return "FAIL"
    if all(c == "PASS" for c in checks):
        return "PASS"
    return None


def _breach(rule: dict[str, Any], lower: float, upper: float) -> tuple[float, str]:
    """(pp beyond the violated limit, side 'max'|'min'), on the conservative value."""
    op = rule["operator"]
    if op in ("max", "range") and not _le(lower, rule["max_value"]):
        return round(lower - rule["max_value"], 6), "max"
    return round(rule["min_value"] - upper, 6), "min"


def _distance_to_limit(rule: dict[str, Any], lower: float, upper: float) -> float:
    """Smallest distance (pp) between the value and a limit of a passing rule."""
    distances = []
    if rule["operator"] in ("max", "range"):
        distances.append(rule["max_value"] - upper)
    if rule["operator"] in ("min", "range"):
        distances.append(lower - rule["min_value"])
    return min(distances)


# ---------------------------------------------------------------------------
# texts
# ---------------------------------------------------------------------------


def _limit_text(rule: dict[str, Any]) -> str:
    if rule["operator"] == "max":
        return f"il tuo limite {format_threshold_it(rule['max_value'])}%"
    if rule["operator"] == "min":
        return f"il tuo minimo {format_threshold_it(rule['min_value'])}%"
    return (
        f"il tuo intervallo {format_threshold_it(rule['min_value'])}–"
        f"{format_threshold_it(rule['max_value'])}%"
    )


def _subject(rule: dict[str, Any], metric: MetricValue | None, label: str) -> str:
    if rule["metric_code"] == "max_single_position_pct" and metric and metric.contributors:
        return str(metric.contributors[0].get("symbol") or label)
    return label


def _short(rule: dict[str, Any]) -> str:
    definition = METRIC_REGISTRY.get(rule["metric_code"])
    return definition.short_label if definition else rule["metric_code"]


def _cannot_verify(rule: dict[str, Any], why: str) -> str:
    return f"Non possiamo verificare il limite {_short(rule)}: {why}"


def _value_text(value: float, precision: int) -> str:
    return f"{format_it(value, precision)}%"


# ---------------------------------------------------------------------------
# data freshness
# ---------------------------------------------------------------------------


def _stale_reason(rule: dict[str, Any], snapshot: DoctorSnapshot, now: datetime) -> str | None:
    max_age = int(rule["max_data_age_days"])
    old: list[str] = []
    for h in snapshot.invested_holdings:
        age = snapshot.price_age_days(h, now)
        if h.asset_id in snapshot.stale_asset_ids or (age is not None and age > max_age):
            old.append(h.symbol)
    if old:
        symbols = ", ".join(sorted(set(old))[:5]) + ("…" if len(set(old)) > 5 else "")
        return _cannot_verify(
            rule, f"quotazioni non aggiornate per {symbols} (più vecchie di {max_age} giorni o ferme)",
        )
    if snapshot.sync_failed:
        return _cannot_verify(rule, "l'ultima sincronizzazione dei prezzi è fallita")
    return None


def _missing_price_share(snapshot: DoctorSnapshot, now: datetime) -> float:
    """Share of the invested value without a usable market price.

    A holding flagged missing (no quote, or valued at average cost) and a
    holding without any price timestamp (its age is unknown, so it can never
    be proven fresh) both count as missing.
    """
    return sum(
        snapshot.weight_of(h) for h in snapshot.invested_holdings
        if h.asset_id in snapshot.missing_price_asset_ids or snapshot.price_age_days(h, now) is None
    )


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------


def _evidence(metric: MetricValue | None, rule: dict[str, Any], snapshot: DoctorSnapshot, calculated_at: str) -> MetricEvidence:
    definition = METRIC_REGISTRY.get(rule["metric_code"])
    if metric is None:
        return MetricEvidence(
            source=definition.source if definition else "unknown",
            denominator=definition.denominator if definition else "",
            denominator_value=None, contributors=[], notes=[],
            quote_as_of=snapshot.quote_as_of, calculated_at=calculated_at,
            methodology_version=METHODOLOGY_VERSION,
        )
    return MetricEvidence(
        source=metric.source,
        denominator=metric.denominator,
        denominator_value=metric.denominator_value,
        contributors=[MetricContributor(**c) for c in metric.contributors],
        notes=list(metric.notes),
        quote_as_of=snapshot.quote_as_of,
        calculated_at=calculated_at,
        methodology_version=METHODOLOGY_VERSION,
    )


def evaluate_rule(
    rule: dict[str, Any],
    metric: MetricValue | None,
    snapshot: DoctorSnapshot,
    *,
    now: datetime,
    calculated_at: str,
) -> RuleResult:
    definition = METRIC_REGISTRY.get(rule["metric_code"])
    label = rule.get("label") or (definition.label if definition else rule["metric_code"])
    precision = int(rule.get("precision", 1))
    base = {
        "rule_id": rule["rule_id"],
        "metric_code": rule["metric_code"],
        "label": label,
        "operator": rule["operator"],
        "min_value": rule.get("min_value"),
        "max_value": rule.get("max_value"),
        "unit": rule.get("unit", "pct"),
        "precision": precision,
        "severity": rule.get("severity", "medium"),
        "actual": metric.value if metric else None,
        "actual_lower": metric.lower if metric else None,
        "actual_upper": metric.upper if metric else None,
        "coverage_pct": metric.coverage_pct if metric else None,
        "quality": metric.quality if metric else "missing",
        "evidence": _evidence(metric, rule, snapshot, calculated_at),
    }

    def result(
        status: str, reason: str, *, near: bool = False, breach: float | None = None, quality: str | None = None,
    ) -> RuleResult:
        fields = dict(base)
        if quality is not None:
            fields["quality"] = quality
        return RuleResult(**fields, status=status, reason=reason, near_limit=near, breach_amount=breach)

    if not rule.get("enabled", True):
        return result("INACTIVE", "Regola disattivata: non viene verificata.")
    if snapshot.is_empty:
        return result("NOT_APPLICABLE", "Portafoglio senza posizioni investite: regola non applicabile.")

    stale = _stale_reason(rule, snapshot, now)
    if stale:
        return result("UNKNOWN", stale)

    missing_share = _missing_price_share(snapshot, now)
    if missing_share > 100.0 - float(rule["min_coverage_pct"]) + EPSILON:
        return result("UNKNOWN", _cannot_verify(
            rule, f"manca la quotazione di mercato per il {format_it(missing_share, 1)}% del valore investito",
        ))

    if metric is None or metric.quality == "missing" and metric.lower is None and metric.upper is None:
        return result("UNKNOWN", _cannot_verify(rule, "dati non disponibili"))

    # PRD D04: with an unclassified/unknown share only the conservative bounds
    # decide (PASS if the upper bound respects the limit, FAIL if the lower
    # bound violates it); the point estimate on the classified part is never
    # used, whatever the coverage. ``min_coverage_pct`` is a gate: below it a
    # result the bounds do not decide is UNKNOWN. The only metric without a
    # meaningful upper bound (TER, ``upper = None`` at partial coverage) may be
    # decided on the covered universe, and only when coverage >= minimum.
    coverage = metric.coverage_pct if metric.coverage_pct is not None else 0.0
    min_coverage = float(rule["min_coverage_pct"])
    coverage_ok = _ge(coverage, min_coverage)
    interval = metric.lower is not None and metric.upper is not None and metric.upper - metric.lower > EPSILON
    open_upper = metric.lower is not None and metric.upper is None
    lower = metric.lower if metric.lower is not None else metric.value
    upper = metric.upper if metric.upper is not None else (metric.value if metric.lower is None else None)
    decided_by = "bounds"
    status = _status_for_interval(rule, lower, upper)
    if status is None and open_upper and metric.value is not None and coverage_ok:
        status = _status_for_interval(rule, metric.value, metric.value)
        lower = upper = metric.value
        decided_by = "covered"
    if status is None:
        if interval:
            range_text = f"valore tra {_value_text(metric.lower, precision)} e {_value_text(metric.upper, precision)}"
        elif metric.lower is not None:
            range_text = f"valore di almeno {_value_text(metric.lower, precision)}, nessun limite superiore noto"
        else:
            range_text = "valore non determinabile"
        if not coverage_ok:
            detail = (
                f"classificato il {format_it(coverage, 1)}% del valore, minimo richiesto "
                f"{format_threshold_it(min_coverage)}%; {range_text}"
            )
            return result("UNKNOWN", _cannot_verify(rule, f"copertura insufficiente ({detail})"))
        return result("UNKNOWN", _cannot_verify(
            rule,
            f"{range_text} (quota non classificata {format_it(max(0.0, 100.0 - coverage), 1)}% "
            f"del valore investito)",
        ))

    subject = _subject(rule, metric, label)
    covered = decided_by == "covered"
    covered_text = f" su {format_threshold_it(round(coverage, 1))}% del portafoglio coperto" if covered else ""
    quality = "partial" if covered else None
    partial = decided_by == "bounds" and metric.lower is not None and metric.upper is not None and (
        metric.upper - metric.lower > EPSILON
    )
    if status == "FAIL":
        breach, side = _breach(rule, lower, upper)
        shown = lower if side == "max" else upper
        bounded = partial or (decided_by == "bounds" and (metric.upper is None or metric.lower is None))
        prefix = ("almeno " if side == "max" else "al massimo ") if bounded else ""
        shown_text = f"{prefix}{_value_text(shown, precision)}{covered_text}"
        if rule["operator"] == "range":
            verb = "sopra il massimo" if side == "max" else "sotto il minimo"
            reason = (
                f"{subject} {shown_text}: fuori dal tuo intervallo "
                f"{format_threshold_it(rule['min_value'])}–{format_threshold_it(rule['max_value'])}%, "
                f"{verb} di {format_it(breach, precision)} {PP}"
            )
        elif side == "max":
            reason = f"{subject} {shown_text}: supera {_limit_text(rule)} di {format_it(breach, precision)} {PP}"
        else:
            reason = f"{subject} {shown_text}: sotto {_limit_text(rule)} di {format_it(breach, precision)} {PP}"
        return result("FAIL", reason, breach=breach, quality=quality)

    distance = _distance_to_limit(rule, lower, upper)
    margin = float(rule.get("warning_margin") or 0.0)
    near = margin > 0 and distance <= margin + EPSILON
    if partial:
        value_part = f"tra {_value_text(lower, precision)} e {_value_text(upper, precision)}"
    else:
        value_part = _value_text(metric.value if decided_by == "bounds" and metric.value is not None else lower, precision)
        value_part += covered_text
    reason = f"{subject} {value_part}: entro {_limit_text(rule)}"
    if near:
        reason += f", a {format_it(max(0.0, distance), precision)} {PP} dalla soglia"
    return result("PASS", reason, near=near, quality=quality)


def _order_key(item: tuple[int, RuleResult]) -> tuple:
    index, r = item
    if r.status == "FAIL":
        return (0, -SEVERITY_RANK.get(r.severity, 0), -(r.breach_amount or 0.0), index)
    if r.status == "UNKNOWN":
        return (1, -SEVERITY_RANK.get(r.severity, 0), 0.0, index)
    if r.status == "PASS" and r.near_limit:
        return (2, -SEVERITY_RANK.get(r.severity, 0), 0.0, index)
    if r.status == "PASS":
        return (3, 0, 0.0, index)
    if r.status == "NOT_APPLICABLE":
        return (4, 0, 0.0, index)
    return (5, 0, 0.0, index)


def summarize(results: list[RuleResult]) -> EvaluationSummary:
    return EvaluationSummary(
        passed=sum(1 for r in results if r.status == "PASS"),
        failed=sum(1 for r in results if r.status == "FAIL"),
        unknown=sum(1 for r in results if r.status == "UNKNOWN"),
        not_applicable=sum(1 for r in results if r.status == "NOT_APPLICABLE"),
        inactive=sum(1 for r in results if r.status == "INACTIVE"),
        near_limit=sum(1 for r in results if r.near_limit),
        total=len(results),
    )


def _utc(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    return now if now.tzinfo else now.replace(tzinfo=UTC)


def evaluate_policy(
    document: dict[str, Any],
    metrics: dict[str, MetricValue],
    snapshot: DoctorSnapshot,
    *,
    now: datetime | None = None,
) -> PolicyEvaluation:
    """Evaluate every rule of ``document`` (normalized first) on ``metrics``.

    Pure: no I/O. ``now`` fixes the clock for the data-age check (tests).
    Raises PolicyValidationError for an invalid document.
    """
    current = _utc(now)
    calculated_at = current.isoformat()
    normalized = normalize_policy_document(document)
    results = [
        evaluate_rule(rule, metrics.get(rule["metric_code"]), snapshot, now=current, calculated_at=calculated_at)
        for rule in normalized["rules"]
    ]
    ordered = [r for _i, r in sorted(enumerate(results), key=_order_key)]
    return PolicyEvaluation(
        results=ordered,
        summary=summarize(ordered),
        calculated_at=calculated_at,
        snapshot_id=snapshot.snapshot_id,
    )


def build_evaluation_response(
    document: dict[str, Any] | None,
    snapshot: DoctorSnapshot,
    metrics: dict[str, MetricValue] | None = None,
    *,
    repo: Any = None,
    policy_id: int | None = None,
    policy_version: int | None = None,
    policy_name: str | None = None,
    now: datetime | None = None,
) -> PolicyEvaluationResponse:
    """``PolicyEvaluationResponse`` of a scope (contract §4).

    ``document`` None -> status ``no_policy``; a snapshot without invested
    holdings -> ``empty_portfolio`` (enabled rules NOT_APPLICABLE). Metrics
    are computed here when not given (pass them to reuse one computation for
    the before/after of a preview).
    """
    current = _utc(now)
    scope = build_scope(snapshot.portfolio_ids) if snapshot.portfolio_ids else None
    common = {
        "scope": scope.model_dump() if scope else {"portfolio_ids": [], "scope_type": "single", "fingerprint": "p:"},
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_name": policy_name,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_as_of": snapshot.quote_as_of,
        "methodology_version": METHODOLOGY_VERSION,
        "data_quality": DataQuality(**snapshot.data_quality),
    }
    if document is None:
        return PolicyEvaluationResponse(
            status="no_policy", calculated_at=current.isoformat(), summary=EvaluationSummary(), results=[], **common,
        )
    if metrics is None:
        metrics = compute_metrics(snapshot, repo, now=current)
    evaluation = evaluate_policy(document, metrics, snapshot, now=current)
    return PolicyEvaluationResponse(
        status="empty_portfolio" if snapshot.is_empty else "ready",
        calculated_at=evaluation.calculated_at,
        summary=evaluation.summary,
        results=evaluation.results,
        **common,
    )
