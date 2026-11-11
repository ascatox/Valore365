"""Report dell'Auditor (TASK-73, contratto §3.7, §4.2, §7.2).

Costruisce il report di un'esecuzione (dict conforme a ``report_schema.json``), lo serializza in
JSON e in Markdown leggibile (riepilogo dei job GitHub, sotto 1 MB), lo valida e ne estrae le righe
salvabili della corsa notturna.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

import jsonschema

from app.version import APP_VERSION

from .registry import RULE_STATUSES, SEVERITIES, Rule

if TYPE_CHECKING:  # pragma: no cover
    from .runner import RunOptions

REPORT_SCHEMA_VERSION = 1
REPORT_SCHEMA_PATH = Path(__file__).with_name("report_schema.json")
MARKDOWN_MAX_BYTES = 1_000_000
_VALUE_MAX_CHARS = 200
_WORST_ORDER = {"fail": 3, "error": 2, "skip": 1, "pass": 0}   # fail > error > skip > pass


class ReportValidationError(ValueError):
    """Report non conforme a report_schema.json (la CLI esce con 2)."""


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))


def load_report_schema() -> dict[str, Any]:
    """Copia dello schema del report (``report_schema.json``)."""
    return copy.deepcopy(_schema())


@lru_cache(maxsize=1)
def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(_schema())


def _timestamp(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _zero_counts() -> dict[str, int]:
    return {status: 0 for status in RULE_STATUSES}


def _severity_rank(severity: str) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


def exit_code_from_results(results: Sequence[dict], *, fail_on: str, strict_known: bool = False) -> int:
    """1 se c'è un fail/error con severità uguale o più grave di ``fail_on`` (§3.6), altrimenti 0."""
    if fail_on not in SEVERITIES:
        raise ValueError(f"soglia di severità sconosciuta: {fail_on!r}")
    threshold = SEVERITIES.index(fail_on)
    for result in results:
        status = result.get("status")
        if status not in ("fail", "error"):
            continue
        if _severity_rank(result.get("severity", "")) > threshold:
            continue
        if status == "fail" and result.get("known_defect") and not strict_known:
            continue
        return 1
    return 0


def _rule_summary(rule: Rule) -> dict[str, Any]:
    return {
        "id": rule.id, "group": rule.group, "severity": rule.severity, "area": rule.area,
        "title": rule.title, "findings": list(rule.findings), "scopes": list(rule.scopes),
        "known_defect": rule.known_defect,
    }


def _list_or_none(values: Sequence[Any] | None, *, sort: bool = False) -> list[Any] | None:
    if values is None:
        return None
    items = list(dict.fromkeys(values))
    return sorted(items) if sort else items


def build_report(
    *, run_id: str, mode: str, user_id: str | None, started_at: datetime, finished_at: datetime,
    options: "RunOptions", rules: Sequence[Rule], scopes: Sequence[dict], results: Sequence[dict],
    tool_calls: dict, deadline_exceeded: bool,
) -> dict:
    from .context import scope_key

    ordered_results = sorted(
        (copy.deepcopy(r) for r in results),
        key=lambda r: (_severity_rank(r["severity"]), r["rule_id"], r["scope_key"]),
    )
    scope_entries = sorted(
        ({"scope": copy.deepcopy(dict(s)), "scope_key": scope_key(s)} for s in scopes),
        key=lambda e: e["scope_key"],
    )

    by_status = _zero_counts()
    by_severity = {severity: _zero_counts() for severity in SEVERITIES}
    by_scope: dict[str, dict[str, int]] = {e["scope_key"]: _zero_counts() for e in scope_entries}
    by_rule: dict[str, dict[str, int]] = {rule.id: _zero_counts() for rule in sorted(rules, key=lambda r: r.id)}
    known_defect_failures = 0
    for result in ordered_results:
        status = result["status"]
        by_status[status] += 1
        by_severity[result["severity"]][status] += 1
        by_scope.setdefault(result["scope_key"], _zero_counts())[status] += 1
        by_rule.setdefault(result["rule_id"], _zero_counts())[status] += 1
        if status == "fail" and result.get("known_defect"):
            known_defect_failures += 1

    duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
    stats = tool_calls or {}
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "mode": mode,
        "app_version": APP_VERSION,
        "started_at": _timestamp(started_at),
        "finished_at": _timestamp(finished_at),
        "duration_ms": duration_ms,
        "user_id": user_id,
        "options": {
            "portfolio_ids": _list_or_none(options.portfolio_ids, sort=True),
            "groups": _list_or_none(options.groups),
            "rule_ids": _list_or_none(options.rule_ids),
            "include_aggregate": bool(options.include_aggregate),
            "include_instruments": bool(options.include_instruments),
            "fail_on": options.fail_on,
            "strict_known": bool(options.strict_known),
        },
        "rules": [_rule_summary(rule) for rule in sorted(rules, key=lambda r: r.id)],
        "scopes": scope_entries,
        "results": ordered_results,
        "counts": {
            "total": len(ordered_results),
            "by_status": by_status,
            "by_severity": by_severity,
            "known_defect_failures": known_defect_failures,
        },
        "by_scope": dict(sorted(by_scope.items())),
        "by_rule": dict(sorted(by_rule.items())),
        "tool_calls": {
            "total": int(stats.get("total", 0)),
            "cache_hits": int(stats.get("cache_hits", 0)),
            "errors": int(stats.get("errors", 0)),
            "by_tool": dict(sorted((stats.get("by_tool") or {}).items())),
        },
        "deadline_exceeded": bool(deadline_exceeded),
        "exit_code": exit_code_from_results(
            ordered_results, fail_on=options.fail_on, strict_known=bool(options.strict_known),
        ),
    }


def report_to_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)


def validate_report(report: dict) -> None:
    """Valida con JSON Schema Draft 2020-12; solleva ``ReportValidationError``."""
    errors = sorted(_validator().iter_errors(report), key=lambda e: list(e.absolute_path))
    if errors:
        lines = []
        for error in errors[:10]:
            where = "/".join(str(p) for p in error.absolute_path) or "(radice)"
            lines.append(f"{where}: {error.message[:300]}")
        more = f" (+{len(errors) - 10} altri)" if len(errors) > 10 else ""
        raise ReportValidationError("report non valido: " + "; ".join(lines) + more)


# -- Markdown ---------------------------------------------------------------------------------

def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _value(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = text.replace("`", "'").replace("\n", " ")
    return text if len(text) <= _VALUE_MAX_CHARS else text[:_VALUE_MAX_CHARS] + "…"


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _duration(ms: int) -> str:
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f} s".replace(".", ",")
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rest} s"


def _evidence_line(evidence: dict) -> str:
    path = evidence.get("path") or "(intero output)"
    line = f"  - `{_value(path)}` ({_value(evidence.get('tool'))}): {_value(evidence.get('observed'))}"
    line += f" → {_value(evidence.get('expected'))}"
    tolerance = evidence.get("tolerance")
    if tolerance is not None:
        line += f", tolleranza ±{_number(float(tolerance))}"
    if evidence.get("note"):
        line += f" — {_value(evidence['note'])}"
    return line


def _render_markdown(report: dict, *, compact: int = 0) -> str:
    """compact: 0 completo; 1 senza tabella delle regole saltate; 2 anche senza tabella degli scope."""
    results = report.get("results") or []
    passed = report.get("exit_code", 1) == 0
    lines: list[str] = [f"# Auditor dei calcoli — {'superato' if passed else 'non superato'}", ""]

    started = str(report.get("started_at", ""))
    when = started[:16].replace("T", " ") + " UTC" if started else "—"
    header = [
        f"versione {report.get('app_version', '?')}",
        f"modalità {report.get('mode', '?')}",
        when,
        f"durata {_duration(int(report.get('duration_ms', 0)))}",
    ]
    if report.get("mode") in ("ci", "local", "agent") and report.get("user_id"):
        header.append(f"utente {report['user_id']}")
    lines.append(" · ".join(header))
    lines.append("")
    if report.get("deadline_exceeded"):
        lines += ["**Superata la durata massima dell'esecuzione:** alcune regole non sono state valutate.", ""]
    options = report.get("options") or {}
    lines.append(
        f"Soglia: {options.get('fail_on', '?')}"
        + (" · difetti noti inclusi" if options.get("strict_known") else " · difetti noti esclusi dall'esito")
    )
    lines.append("")

    counts = report.get("counts") or {}
    by_severity = counts.get("by_severity") or {}
    lines += ["| severità | pass | fail | skip | error |", "|---|---:|---:|---:|---:|"]
    for severity in SEVERITIES:
        row = by_severity.get(severity) or _zero_counts()
        lines.append(f"| {severity} | " + " | ".join(str(row.get(s, 0)) for s in RULE_STATUSES) + " |")
    total = counts.get("by_status") or _zero_counts()
    lines.append("| **totale** | " + " | ".join(f"**{total.get(s, 0)}**" for s in RULE_STATUSES) + " |")
    lines += ["", f"Difetti noti (fail su regole con `known_defect`): {counts.get('known_defect_failures', 0)}", ""]

    rules_by_id = {r["id"]: r for r in report.get("rules") or []}
    lines += ["## Fallimenti ed errori", ""]
    bad = [r for r in results if r.get("status") in ("fail", "error")]
    if not bad:
        lines += ["Nessun fallimento e nessun errore.", ""]
    for severity in SEVERITIES:
        sev_results = [r for r in bad if r.get("severity") == severity]
        if not sev_results:
            continue
        lines += [f"### {severity}", ""]
        current_rule = None
        for result in sev_results:
            if result["rule_id"] != current_rule:
                current_rule = result["rule_id"]
                rule = rules_by_id.get(current_rule, {})
                findings = ", ".join(rule.get("findings") or []) or "—"
                title = f"#### {_cell(result.get('title'))} (`{current_rule}`)"
                lines += [title, "", f"Finding: {findings}"
                          + (f" · difetto noto {result['known_defect']}" if result.get("known_defect") else ""), ""]
            status = result["status"]
            lines.append(
                f"- **{_cell(result['scope_key'])}** — {status} (`{result.get('reason_code')}`): "
                f"{_cell(result.get('reason'))}"
            )
            for evidence in result.get("evidence") or []:
                lines.append(_evidence_line(evidence))
            if result.get("evidence_truncated"):
                lines.append("  - … evidenze troncate dal motore")
        lines.append("")

    skipped = [r for r in results if r.get("status") == "skip"]
    lines += ["## Regole saltate", ""]
    if not skipped:
        lines += ["Nessuna regola saltata.", ""]
    elif compact >= 1:
        lines += [f"{len(skipped)} esiti saltati: tabella omessa per restare sotto 1 MB (vedi il report JSON).", ""]
    else:
        lines += ["| regola | scope | codice | motivo |", "|---|---|---|---|"]
        for result in skipped:
            lines.append(
                f"| `{result['rule_id']}` | {_cell(result['scope_key'])} | `{result.get('reason_code')}` | "
                f"{_cell(result.get('reason'))} |"
            )
        lines.append("")

    by_scope = report.get("by_scope") or {}
    lines += ["## Esiti per scope", ""]
    if compact >= 2:
        lines += [f"{len(by_scope)} scope: tabella omessa per restare sotto 1 MB (vedi il report JSON).", ""]
    elif not by_scope:
        lines += ["Nessuno scope.", ""]
    else:
        lines += ["| scope | pass | fail | skip | error |", "|---|---:|---:|---:|---:|"]
        for key, row in by_scope.items():
            lines.append(f"| {_cell(key)} | " + " | ".join(str(row.get(s, 0)) for s in RULE_STATUSES) + " |")
        lines.append("")

    calls = report.get("tool_calls") or {}
    lines += [
        "## Chiamate ai tool", "",
        f"Totale: {calls.get('total', 0)} · dalla memo: {calls.get('cache_hits', 0)} · errori: {calls.get('errors', 0)}",
        "",
    ]
    return "\n".join(lines)


def report_to_markdown(report: dict) -> str:
    """Markdown in italiano (§3.7), sotto 1 MB.

    Le evidenze di ``pass`` e ``skip`` non sono mai riportate; oltre il limite si omettono prima la
    tabella delle regole saltate, poi quella per scope; le evidenze di fail/error restano.
    """
    for compact in (0, 1, 2):
        text = _render_markdown(report, compact=compact)
        if len(text.encode("utf-8")) <= MARKDOWN_MAX_BYTES:
            return text
    marker = "\n\n… report troncato a 1 MB: il dettaglio completo è nel report JSON.\n"
    budget = MARKDOWN_MAX_BYTES - len(marker.encode("utf-8"))
    return text.encode("utf-8")[:budget].decode("utf-8", errors="ignore") + marker


# -- Privacy (§7.2) ---------------------------------------------------------------------------

def _member_ids(scope: dict) -> list[int]:
    kind = scope.get("kind")
    if kind in ("portfolio", "instrument"):
        return [int(scope["portfolio_id"])]
    return [int(i) for i in scope.get("portfolio_ids") or []]


def privacy_rows(report: dict) -> list[dict]:
    """Righe salvabili della corsa notturna: nessun simbolo, importo, evidenza o testo."""
    rows: dict[tuple[int, str, str], dict[str, Any]] = {}
    for result in report.get("results") or []:
        scope = result.get("scope") or {}
        kind = scope.get("kind")
        status = result.get("status")
        for pid in _member_ids(scope):
            key = (pid, result["rule_id"], kind)
            current = rows.get(key)
            if current is None or _WORST_ORDER[status] > _WORST_ORDER[current["status"]]:
                rows[key] = {
                    "portfolio_id": pid, "rule_id": result["rule_id"], "scope_kind": kind,
                    "status": status, "severity": result["severity"],
                }
    return [rows[key] for key in sorted(rows)]
