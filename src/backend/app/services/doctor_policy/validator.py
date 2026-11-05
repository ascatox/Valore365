"""Strict validation and normalization of policy documents (contract §3).

The document is plain JSON data: numbers must be JSON numbers (a string
``"35"`` is rejected, nothing is ever parsed or evaluated as an expression),
unknown fields are errors, metric codes come from the registry allowlist.

``validate_policy_document`` returns every error found, each with a path such
as ``rules[0].max_value``; ``normalize_policy_document`` returns the document
with every default filled in and every number as float (raises
``PolicyValidationError`` when it is not valid). ``document_hash`` and
``diff_documents`` work on normalized documents.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from ...schemas.doctor_policy import FieldError
from .metrics import METRIC_REGISTRY, format_threshold_it

SCHEMA_VERSION = 1
MAX_RULES = 20
MAX_LABEL_LENGTH = 80
EPSILON = 1e-9
# Used with fullmatch: "$" would also accept a trailing "\n".
RULE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
SEVERITIES = ("low", "medium", "high")
OPERATORS = ("min", "max", "range")

DOCUMENT_FIELDS = frozenset({"schema_version", "rules"})
RULE_FIELDS = (
    "rule_id", "metric_code", "operator", "min_value", "max_value", "unit", "precision",
    "severity", "warning_margin", "min_coverage_pct", "max_data_age_days", "enabled", "label",
)
DEFAULT_SEVERITY = "medium"
DEFAULT_MIN_COVERAGE_PCT = 80.0
DEFAULT_MAX_DATA_AGE_DAYS = 5
MAX_DATA_AGE_DAYS = 365
ASSET_CLASS_METRICS = ("equity_weight_pct", "bond_weight_pct", "gold_weight_pct")


class PolicyValidationError(ValueError):
    def __init__(self, errors: list[FieldError]):
        self.errors = errors
        super().__init__("; ".join(f"{e.field}: {e.message}" for e in errors) or "Policy non valida")


def _err(field: str, code: str, message: str) -> FieldError:
    return FieldError(field=field, code=code, message=message)


def _is_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    # Any JSON integer is a number (a huge one is out of range, not a 500:
    # float(10**400) would raise OverflowError).
    return isinstance(value, int) or math.isfinite(value)


def _is_int(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value) and value.is_integer()


def _number(
    errors: list[FieldError], path: str, value: Any, *, low: float, high: float, default: float | None,
) -> float | None:
    if value is None:
        return default
    if not _is_number(value):
        errors.append(_err(path, "invalid_type", "Deve essere un numero."))
        return None
    try:
        number = float(value)
    except OverflowError:
        number = math.inf if value > 0 else -math.inf
    if number < low - EPSILON or number > high + EPSILON:
        errors.append(_err(
            path, "out_of_range",
            f"Deve essere compreso fra {format_threshold_it(low)} e {format_threshold_it(high)}.",
        ))
        return None
    return number


def _validate_rule(raw: Any, index: int, errors: list[FieldError]) -> dict[str, Any] | None:
    base = f"rules[{index}]"
    if not isinstance(raw, dict):
        errors.append(_err(base, "invalid_type", "Ogni regola deve essere un oggetto."))
        return None
    for key in raw:
        if key not in RULE_FIELDS:
            errors.append(_err(f"{base}.{key}", "extra_field", f"Campo non ammesso: {key}."))
    start = len(errors)

    rule_id = raw.get("rule_id")
    if rule_id is None:
        errors.append(_err(f"{base}.rule_id", "required", "Identificativo della regola obbligatorio."))
    elif not isinstance(rule_id, str) or not RULE_ID_PATTERN.fullmatch(rule_id):
        errors.append(_err(
            f"{base}.rule_id", "invalid_format",
            "Usa da 1 a 40 caratteri: lettere minuscole, cifre, '-' o '_' (inizia con lettera o cifra).",
        ))

    metric_code = raw.get("metric_code")
    definition = METRIC_REGISTRY.get(metric_code) if isinstance(metric_code, str) else None
    if metric_code is None:
        errors.append(_err(f"{base}.metric_code", "required", "Metrica obbligatoria."))
    elif definition is None:
        errors.append(_err(f"{base}.metric_code", "unknown_metric", f"Metrica non supportata: {metric_code!r}."))

    operator = raw.get("operator")
    if operator is None:
        errors.append(_err(f"{base}.operator", "required", "Operatore obbligatorio."))
    elif operator not in OPERATORS:
        errors.append(_err(f"{base}.operator", "invalid_operator", "Operatore ammesso: min, max o range."))
    elif definition is not None and operator not in definition.operators:
        errors.append(_err(
            f"{base}.operator", "operator_not_allowed",
            f"Per {definition.label} sono ammessi: {', '.join(definition.operators)}.",
        ))

    min_value = _number(errors, f"{base}.min_value", raw.get("min_value"), low=0.0, high=100.0, default=None)
    max_value = _number(errors, f"{base}.max_value", raw.get("max_value"), low=0.0, high=100.0, default=None)
    if operator in ("min", "range") and raw.get("min_value") is None:
        errors.append(_err(f"{base}.min_value", "required", "Soglia minima obbligatoria per questo operatore."))
    if operator in ("max", "range") and raw.get("max_value") is None:
        errors.append(_err(f"{base}.max_value", "required", "Soglia massima obbligatoria per questo operatore."))
    if operator == "min" and raw.get("max_value") is not None:
        errors.append(_err(f"{base}.max_value", "not_allowed", "Con l'operatore min la soglia massima va lasciata vuota."))
    if operator == "max" and raw.get("min_value") is not None:
        errors.append(_err(f"{base}.min_value", "not_allowed", "Con l'operatore max la soglia minima va lasciata vuota."))
    if operator == "range" and min_value is not None and max_value is not None and min_value > max_value + EPSILON:
        errors.append(_err(f"{base}.min_value", "min_gt_max", "La soglia minima non può superare la massima."))

    unit = raw.get("unit")
    expected_unit = definition.unit if definition is not None else "pct"
    if unit is not None and unit != expected_unit:
        errors.append(_err(f"{base}.unit", "invalid_unit", f"Unità ammessa: {expected_unit}."))

    precision = raw.get("precision")
    if precision is None:
        precision = definition.default_precision if definition is not None else 1
    elif not _is_int(precision):
        errors.append(_err(f"{base}.precision", "invalid_type", "Deve essere un intero."))
    elif not 0 <= int(precision) <= 3:
        errors.append(_err(f"{base}.precision", "out_of_range", "Deve essere compreso fra 0 e 3."))

    severity = raw.get("severity", DEFAULT_SEVERITY)
    if severity is None:
        severity = DEFAULT_SEVERITY
    if severity not in SEVERITIES:
        errors.append(_err(f"{base}.severity", "invalid_value", "Severità ammessa: low, medium o high."))

    default_margin = definition.default_warning_margin if definition is not None else 2.0
    warning_margin = _number(
        errors, f"{base}.warning_margin", raw.get("warning_margin"), low=0.0, high=100.0, default=default_margin,
    )
    min_coverage = _number(
        errors, f"{base}.min_coverage_pct", raw.get("min_coverage_pct"), low=0.0, high=100.0,
        default=DEFAULT_MIN_COVERAGE_PCT,
    )

    max_age = raw.get("max_data_age_days")
    if max_age is None:
        max_age = DEFAULT_MAX_DATA_AGE_DAYS
    elif not _is_int(max_age):
        errors.append(_err(f"{base}.max_data_age_days", "invalid_type", "Deve essere un intero (giorni)."))
    elif not 1 <= int(max_age) <= MAX_DATA_AGE_DAYS:
        errors.append(_err(f"{base}.max_data_age_days", "out_of_range", f"Deve essere fra 1 e {MAX_DATA_AGE_DAYS} giorni."))

    enabled = raw.get("enabled", True)
    if enabled is None:
        enabled = True
    if not isinstance(enabled, bool):
        errors.append(_err(f"{base}.enabled", "invalid_type", "Deve essere true o false."))

    label = raw.get("label")
    if label is not None:
        if not isinstance(label, str):
            errors.append(_err(f"{base}.label", "invalid_type", "Deve essere un testo."))
        else:
            label = label.strip() or None
            if label is not None and len(label) > MAX_LABEL_LENGTH:
                errors.append(_err(f"{base}.label", "too_long", f"Al massimo {MAX_LABEL_LENGTH} caratteri."))

    if len(errors) > start or any(e.field.startswith(f"{base}.") for e in errors):
        return None
    return {
        "rule_id": rule_id,
        "metric_code": metric_code,
        "operator": operator,
        "min_value": min_value if operator in ("min", "range") else None,
        "max_value": max_value if operator in ("max", "range") else None,
        "unit": expected_unit,
        "precision": int(precision),
        "severity": severity,
        "warning_margin": float(warning_margin),
        "min_coverage_pct": float(min_coverage),
        "max_data_age_days": int(max_age),
        "enabled": enabled,
        "label": label,
    }


def _feasibility(rules: list[tuple[int, dict[str, Any]]], errors: list[FieldError]) -> None:
    """Only the certain contradictions among enabled rules."""
    enabled = {r["metric_code"]: (i, r) for i, r in rules if r["enabled"]}

    minima = []
    for code in ASSET_CLASS_METRICS:
        item = enabled.get(code)
        if item and item[1]["min_value"] is not None:
            minima.append((code, item[1]["min_value"]))
    total_min = sum(v for _c, v in minima)
    if total_min > 100.0 + EPSILON:
        parts = " + ".join(f"{format_threshold_it(v)}%" for _c, v in minima)
        errors.append(_err(
            "rules", "infeasible",
            f"I minimi di azioni, obbligazioni e oro sommano a {format_threshold_it(total_min)}% "
            f"({parts}): nessun portafoglio può rispettarli insieme.",
        ))

    single = enabled.get("max_single_position_pct")
    top3 = enabled.get("top3_positions_pct")
    if single and top3:
        single_max = single[1]["max_value"]
        top3_max = top3[1]["max_value"]
        if single_max is not None and top3_max is not None and top3_max < single_max - EPSILON:
            errors.append(_err(
                f"rules[{top3[0]}].max_value", "inconsistent",
                f"Il limite sulle prime tre posizioni ({format_threshold_it(top3_max)}%) è inferiore al limite "
                f"sulla singola posizione ({format_threshold_it(single_max)}%): le prime tre includono la più grande.",
            ))
        top3_min = top3[1]["min_value"]
        if single_max is not None and top3_min is not None and single_max * 3 < top3_min - EPSILON:
            errors.append(_err(
                f"rules[{top3[0]}].min_value", "infeasible",
                "Il minimo sulle prime tre posizioni supera tre volte il massimo sulla singola posizione.",
            ))


def _validate(doc: Any) -> tuple[dict[str, Any] | None, list[FieldError]]:
    errors: list[FieldError] = []
    if not isinstance(doc, dict):
        return None, [_err("document", "invalid_type", "Il documento deve essere un oggetto JSON.")]
    for key in doc:
        if key not in DOCUMENT_FIELDS:
            errors.append(_err(str(key), "extra_field", f"Campo non ammesso: {key}."))

    version = doc.get("schema_version", SCHEMA_VERSION)
    if not _is_int(version) or int(version) != SCHEMA_VERSION:
        errors.append(_err("schema_version", "unsupported_version", f"Versione dello schema supportata: {SCHEMA_VERSION}."))

    raw_rules = doc.get("rules", [])
    if raw_rules is None:
        raw_rules = []
    if not isinstance(raw_rules, list):
        errors.append(_err("rules", "invalid_type", "Le regole devono essere una lista."))
        return None, errors
    if len(raw_rules) > MAX_RULES:
        errors.append(_err("rules", "too_many_rules", f"Al massimo {MAX_RULES} regole."))
        return None, errors

    normalized: list[tuple[int, dict[str, Any]]] = []
    seen_ids: dict[str, int] = {}
    seen_metrics: dict[str, int] = {}
    for index, raw in enumerate(raw_rules):
        if isinstance(raw, dict):
            rule_id = raw.get("rule_id")
            if isinstance(rule_id, str):
                if rule_id in seen_ids:
                    errors.append(_err(f"rules[{index}].rule_id", "duplicate", f"rule_id già usato in rules[{seen_ids[rule_id]}]."))
                else:
                    seen_ids[rule_id] = index
            code = raw.get("metric_code")
            if isinstance(code, str) and code in METRIC_REGISTRY:
                if code in seen_metrics:
                    errors.append(_err(
                        f"rules[{index}].metric_code", "duplicate",
                        f"Metrica già usata in rules[{seen_metrics[code]}]: una regola per metrica.",
                    ))
                else:
                    seen_metrics[code] = index
        rule = _validate_rule(raw, index, errors)
        if rule is not None:
            normalized.append((index, rule))

    if not errors:
        _feasibility(normalized, errors)
    if errors:
        return None, errors
    return {"schema_version": SCHEMA_VERSION, "rules": [r for _i, r in normalized]}, []


def validate_policy_document(doc: Any) -> list[FieldError]:
    """Every validation error of ``doc`` (empty list = valid)."""
    return _validate(doc)[1]


def validate_and_normalize(doc: Any) -> tuple[dict[str, Any] | None, list[FieldError]]:
    """(normalized document or None, errors) in one pass."""
    return _validate(doc)


def normalize_policy_document(doc: Any) -> dict[str, Any]:
    """Normalized copy of a valid document (defaults filled, numbers as float).

    Raises PolicyValidationError when the document is not valid.
    """
    normalized, errors = _validate(doc)
    if errors or normalized is None:
        raise PolicyValidationError(errors)
    return normalized


def canonical_json(doc: Any) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def document_hash(doc: Any) -> str:
    """sha256 (hex) of the canonical JSON of a document.

    A valid document is normalized first, so ``35`` and ``35.0`` or a missing
    default give the same hash; an invalid one is hashed as given.
    """
    normalized, errors = _validate(doc)
    payload = normalized if not errors and normalized is not None else doc
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _rules_by_metric(doc: Any) -> dict[str, dict[str, Any]]:
    if not doc:
        return {}
    normalized, errors = _validate(doc)
    source = normalized if not errors and normalized is not None else doc
    rules = source.get("rules") if isinstance(source, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for rule in rules or []:
        if isinstance(rule, dict) and isinstance(rule.get("metric_code"), str):
            out.setdefault(rule["metric_code"], rule)
    return out


def diff_documents(before: Any, after: Any) -> list[dict[str, Any]]:
    """Rule-level diff (contract §5): added / removed / modified by metric_code.

    Rules are matched by ``metric_code`` (unique within a document: one rule
    per metric), so a rule whose ``rule_id`` changed while staying on the same
    metric (e.g. renamed by the Copilot) is "modified", not added + removed.
    ``rule_id`` of an entry is the one of ``after`` (``before`` for removals).

    Order: rules of ``after`` in their order, then the removed ones in the
    order of ``before``. ``before`` None (no current policy) = all added.
    """
    old = _rules_by_metric(before)
    new = _rules_by_metric(after)
    diff: list[dict[str, Any]] = []
    for metric_code, rule in new.items():
        previous = old.get(metric_code)
        if previous is None:
            diff.append({"rule_id": rule.get("rule_id"), "metric_code": metric_code, "change": "added", "before": None, "after": rule})
        elif canonical_json(previous) != canonical_json(rule):
            diff.append({"rule_id": rule.get("rule_id"), "metric_code": metric_code, "change": "modified", "before": previous, "after": rule})
    for metric_code, rule in old.items():
        if metric_code not in new:
            diff.append({"rule_id": rule.get("rule_id"), "metric_code": metric_code, "change": "removed", "before": rule, "after": None})
    return diff
