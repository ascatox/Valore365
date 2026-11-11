"""CLI dell'Auditor (TASK-73, contratto §3.8).

    python -m app.services.auditor --user USER_ID [--portfolio ID]... [--group A]... [--rule ID]...
        [--no-aggregate] [--no-instruments] [--fail-on P0|P1|P2] [--strict-known]
        [--mode ci|local|agent] [--format markdown|json] [--json-out PATH] [--md-out PATH]
        [--rule-timeout-s S] [--max-duration-s S] [--max-workers N] [--list-rules]

Codici di uscita: 0 nessun fail/error alla soglia; 1 almeno uno; 2 errore d'uso o di
configurazione prima della valutazione (argomenti, regole, utente senza portafogli, database,
report non valido). Non importa esplicitamente ``app.main`` e non ne avvia il ciclo di vita
(scheduler, migrazioni): usa solo repository e servizi tramite ``build_tool_dependencies``.
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import uuid
from pathlib import Path

from .context import AuditContext, AuditToolError, ScopeSelectionError, build_tool_dependencies
from .registry import GROUPS, SEVERITIES, RuleRegistrationError, load_rules, select_rules
from .report import ReportValidationError, report_to_json, report_to_markdown, validate_report
from .runner import RunOptions, exit_code_for, run_audit

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_USAGE = 2

logger = logging.getLogger("app.services.auditor")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D401 - argparse API
        self.print_usage(sys.stderr)
        raise _UsageError(message)


class _UsageError(Exception):
    pass


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"intero non valido: {text!r}") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError(f"deve essere positivo: {text!r}")
    return value


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"numero non valido: {text!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"deve essere positivo: {text!r}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="python -m app.services.auditor", description="Auditor dei calcoli di Valore365")
    parser.add_argument("--user", dest="user_id", help="utente proprietario dei portafogli da verificare")
    parser.add_argument("--portfolio", dest="portfolio_ids", action="append", type=_positive_int, metavar="ID",
                        help="portafoglio (ripetibile; default: tutti quelli dell'utente)")
    parser.add_argument("--group", dest="groups", action="append", choices=GROUPS, help="gruppo di regole (ripetibile)")
    parser.add_argument("--rule", dest="rule_ids", action="append", metavar="RULE_ID", help="id di regola (ripetibile)")
    parser.add_argument("--no-aggregate", dest="include_aggregate", action="store_false")
    parser.add_argument("--no-instruments", dest="include_instruments", action="store_false")
    parser.add_argument("--fail-on", choices=SEVERITIES, default="P1")
    parser.add_argument("--strict-known", action="store_true")
    parser.add_argument("--mode", choices=("ci", "local", "agent"), default="local")
    parser.add_argument("--format", dest="output_format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--json-out", type=Path, metavar="PATH")
    parser.add_argument("--md-out", type=Path, metavar="PATH")
    parser.add_argument("--rule-timeout-s", type=_positive_float, metavar="S")
    parser.add_argument("--max-duration-s", type=_positive_float, default=1800.0, metavar="S")
    parser.add_argument("--max-workers", type=_positive_int, default=1, metavar="N")
    parser.add_argument("--list-rules", action="store_true", help="elenca le regole ed esce")
    return parser


def _err(message: str) -> None:
    print(f"auditor: {message}", file=sys.stderr)


def _list_rules(rules) -> None:
    for rule in rules:
        print("\t".join([rule.id, rule.group, rule.severity, rule.title, rule.known_defect or "-"]))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        _err(str(exc))
        return EXIT_USAGE
    except SystemExit as exc:  # --help
        return int(exc.code or 0)

    try:
        rules = load_rules()
    except Exception as exc:  # noqa: BLE001 - regola non valida o modulo che non si importa
        _err(f"caricamento delle regole fallito: {type(exc).__name__}: {exc}")
        return EXIT_USAGE

    try:
        selected = select_rules(rules, groups=args.groups, rule_ids=args.rule_ids)
    except RuleRegistrationError as exc:
        _err(str(exc))
        return EXIT_USAGE

    if args.list_rules:
        _list_rules(selected)
        return EXIT_OK
    if not args.user_id:
        _err("--user è obbligatorio")
        return EXIT_USAGE
    if not selected:
        _err("nessuna regola caricata o selezionata")
        return EXIT_USAGE

    try:
        deps = build_tool_dependencies(offline=True)
    except Exception as exc:  # noqa: BLE001 - configurazione o database
        _err(f"dipendenze non disponibili: {type(exc).__name__}: {exc}")
        return EXIT_USAGE

    ctx = AuditContext(deps, args.user_id, run_id=uuid.uuid4().hex, mode=args.mode)
    try:
        portfolios = ctx.portfolios()
    except AuditToolError as exc:
        _err(f"list_portfolios non raggiungibile: {exc.message}")
        return EXIT_USAGE
    if not portfolios:
        _err(f"l'utente {args.user_id} non ha portafogli")
        return EXIT_USAGE

    options = RunOptions(
        mode=args.mode,
        portfolio_ids=args.portfolio_ids,
        groups=args.groups,
        rule_ids=args.rule_ids,
        include_aggregate=args.include_aggregate,
        include_instruments=args.include_instruments,
        fail_on=args.fail_on,
        strict_known=args.strict_known,
        rule_timeout_s=args.rule_timeout_s,
        max_duration_s=args.max_duration_s,
        max_workers=args.max_workers,
    )
    try:
        report = run_audit(ctx, rules, options)
    except (ScopeSelectionError, RuleRegistrationError) as exc:
        _err(str(exc))
        return EXIT_USAGE
    except AuditToolError as exc:
        _err(f"tool non raggiungibile prima della valutazione: {exc}")
        return EXIT_USAGE

    try:
        validate_report(report)
    except ReportValidationError as exc:
        _err(str(exc))
        return EXIT_USAGE

    json_text = report_to_json(report)
    markdown = report_to_markdown(report)
    try:
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json_text + "\n", encoding="utf-8")
        if args.md_out:
            args.md_out.parent.mkdir(parents=True, exist_ok=True)
            args.md_out.write_text(markdown + "\n", encoding="utf-8")
    except OSError as exc:
        _err(f"scrittura del report fallita: {exc}")
        return EXIT_USAGE
    sys.stdout.write((json_text if args.output_format == "json" else markdown) + "\n")
    sys.stdout.flush()
    return exit_code_for(report, fail_on=options.fail_on, strict_known=options.strict_known)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())
