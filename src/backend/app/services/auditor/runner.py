"""Esecutore dell'Auditor (TASK-73, contratto §3.6).

Valuta ogni regola su ogni scope compatibile, isolando eccezioni, timeout ed errori dei tool: una
regola che fallisce male produce ``error`` sul proprio risultato e non ferma le altre.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Sequence

import jsonschema

from .context import AuditContext, AuditToolError, discover_scopes, scope_key
from .registry import MAX_EVIDENCE_ITEMS, Rule, select_rules
from . import report as report_module

logger = logging.getLogger(__name__)

_MAX_REASON_CHARS = 300


@dataclass
class RunOptions:
    mode: str = "local"                         # "ci" | "local" | "nightly" | "agent"
    portfolio_ids: list[int] | None = None      # None = tutti i portafogli dell'utente
    groups: list[str] | None = None
    rule_ids: list[str] | None = None
    include_aggregate: bool = True
    include_instruments: bool = True
    fail_on: str = "P1"                         # soglia: conta fail/error con severità <= soglia
    strict_known: bool = False                  # True: anche i difetti noti contano per l'uscita
    rule_timeout_s: float | None = None         # tetto al timeout di ogni regola
    max_duration_s: float = 1800.0              # scadenza dell'intera esecuzione
    max_workers: int = 1                        # regole valutate in parallelo


@lru_cache(maxsize=1)
def _outcome_validator() -> jsonschema.Draft202012Validator:
    schema = report_module.load_report_schema()
    return jsonschema.Draft202012Validator({"$ref": "#/$defs/Outcome", "$defs": schema["$defs"]})


def _format_seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _truncate(text: str, limit: int = _MAX_REASON_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _result(
    rule: Rule, scope: dict, *, status: str, reason_code: str | None, reason: str | None,
    evidence: list | None = None, duration_ms: int = 0,
) -> dict[str, Any]:
    evidence = list(evidence or [])
    truncated = len(evidence) > MAX_EVIDENCE_ITEMS
    return {
        "rule_id": rule.id,
        "group": rule.group,
        "severity": rule.severity,
        "area": rule.area,
        "title": rule.title,
        "scope": json.loads(json.dumps(scope)),
        "scope_key": scope_key(scope),
        "status": status,
        "reason_code": reason_code,
        "reason": reason,
        "evidence": evidence[:MAX_EVIDENCE_ITEMS],
        "evidence_truncated": truncated,
        "duration_ms": max(0, int(duration_ms)),
        "known_defect": rule.known_defect,
    }


def _tool_error_evidence(exc: AuditToolError) -> list[dict[str, Any]]:
    try:
        args = json.loads(json.dumps(exc.args, default=str))
    except (TypeError, ValueError):
        args = {}
    if not isinstance(args, dict):
        args = {}
    return [{
        "tool": exc.tool or "?", "args": args, "path": "", "observed": None, "expected": None,
        "tolerance": None, "note": _truncate(exc.message),
    }]


def _validate_outcome(outcome: Any) -> tuple[dict[str, Any] | None, str | None]:
    """(esito normalizzato, None) oppure (None, motivo dell'invalidità)."""
    if not isinstance(outcome, dict):
        return None, f"check ha restituito {type(outcome).__name__}, non un dict"
    try:
        normalized = json.loads(json.dumps(outcome, allow_nan=False))
    except (TypeError, ValueError) as exc:
        return None, f"esito non serializzabile in JSON ({type(exc).__name__}: {exc})"
    error = jsonschema.exceptions.best_match(_outcome_validator().iter_errors(normalized))
    if error is not None:
        where = "/".join(str(p) for p in error.absolute_path) or "esito"
        return None, f"{where}: {error.message}"
    return normalized, None


def _run_in_thread(fn, timeout_s: float) -> tuple[bool, Any, BaseException | None]:
    """(finito, valore, eccezione). Thread daemon: se scade viene abbandonato senza bloccare."""
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - riportata al chiamante
            box["error"] = exc

    thread = threading.Thread(target=target, name="auditor-rule", daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        return False, None, None
    return True, box.get("value"), box.get("error")


def _evaluate(rule: Rule, ctx: AuditContext, scope: dict, *, timeout_s: float,
              deadline_cut: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    finished, outcome, exc = _run_in_thread(lambda: rule.check(ctx, scope), timeout_s)
    duration_ms = int((time.monotonic() - started) * 1000)
    if not finished:
        if deadline_cut:
            return _result(rule, scope, status="error", reason_code="deadline_exceeded",
                           reason="Superata la durata massima dell'esecuzione.", duration_ms=duration_ms)
        return _result(rule, scope, status="error", reason_code="timeout",
                       reason=f"Superato il limite di {_format_seconds(timeout_s)} s.", duration_ms=duration_ms)
    if exc is not None:
        if isinstance(exc, AuditToolError):
            return _result(rule, scope, status="error", reason_code="tool_error",
                           reason=_truncate(f"Errore del tool {exc.tool}: {exc.message}"),
                           evidence=_tool_error_evidence(exc), duration_ms=duration_ms)
        if not isinstance(exc, Exception):
            raise exc  # KeyboardInterrupt, SystemExit: non si isolano
        return _result(rule, scope, status="error", reason_code="exception",
                       reason=f"{type(exc).__name__}: {_truncate(str(exc))}", duration_ms=duration_ms)
    normalized, problem = _validate_outcome(outcome)
    if normalized is None:
        return _result(rule, scope, status="error", reason_code="invalid_outcome",
                       reason=_truncate(f"Esito non valido: {problem}"), duration_ms=duration_ms)
    return _result(rule, scope, status=normalized["status"], reason_code=normalized["reason_code"],
                   reason=normalized["reason"], evidence=normalized["evidence"], duration_ms=duration_ms)


def evaluate_rule(rule: Rule, ctx: AuditContext, scope: dict, *, timeout_s: float) -> dict:
    """RuleResult (§4.1) di ``rule`` su ``scope``; non solleva per errori della regola."""
    return _evaluate(rule, ctx, scope, timeout_s=timeout_s)


def _effective_timeout(rule: Rule, options: RunOptions) -> float:
    cap = options.rule_timeout_s if options.rule_timeout_s else math.inf
    return min(rule.timeout_s, cap)


def _deadline_result(rule: Rule, scope: dict) -> dict[str, Any]:
    return _result(rule, scope, status="error", reason_code="deadline_exceeded",
                   reason="Superata la durata massima dell'esecuzione: regola non valutata.")


def run_audit(ctx: AuditContext, rules: Sequence[Rule], options: RunOptions) -> dict:
    """Esegue le regole selezionate su tutti gli scope e restituisce il report (§4.2)."""
    started_at = datetime.now(UTC)
    started = time.monotonic()
    deadline = started + float(options.max_duration_s)
    selected = select_rules(rules, groups=options.groups, rule_ids=options.rule_ids)
    scopes = discover_scopes(
        ctx, portfolio_ids=options.portfolio_ids,
        include_aggregate=options.include_aggregate, include_instruments=options.include_instruments,
    )
    pairs = [(rule, scope) for rule in selected for scope in scopes if scope["kind"] in rule.scopes]
    deadline_hit = threading.Event()

    def evaluate_pair(pair: tuple[Rule, dict]) -> dict[str, Any]:
        rule, scope = pair
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            deadline_hit.set()
            return _deadline_result(rule, scope)
        timeout_s = _effective_timeout(rule, options)
        cut = remaining < timeout_s
        result = _evaluate(rule, ctx, scope, timeout_s=min(timeout_s, remaining), deadline_cut=cut)
        if result["reason_code"] == "deadline_exceeded":
            deadline_hit.set()
        return result

    workers = max(1, int(options.max_workers or 1))
    if workers == 1 or len(pairs) <= 1:
        results = [evaluate_pair(pair) for pair in pairs]
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="auditor") as pool:
            results = list(pool.map(evaluate_pair, pairs))

    finished_at = datetime.now(UTC)
    logger.info(
        "Auditor run %s: %d regole, %d scope, %d risultati in %.1f s",
        ctx.run_id, len(selected), len(scopes), len(results), time.monotonic() - started,
    )
    return report_module.build_report(
        run_id=ctx.run_id,
        mode=options.mode,
        user_id=None if options.mode == "nightly" else ctx.user_id,
        started_at=started_at,
        finished_at=finished_at,
        options=options,
        rules=selected,
        scopes=scopes,
        results=results,
        tool_calls=ctx.call_stats(),
        deadline_exceeded=deadline_hit.is_set(),
    )


def exit_code_for(report: dict, *, fail_on: str, strict_known: bool = False) -> int:
    return report_module.exit_code_from_results(report.get("results") or [], fail_on=fail_on, strict_known=strict_known)
