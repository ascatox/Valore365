"""Registro delle regole dell'Auditor (TASK-73, contratto §3.1-3.2).

Una regola si dichiara come ``dict`` nella lista ``RULES`` del modulo del proprio gruppo
(``rules/<modulo>.py``); ``load_rules`` importa i moduli di ``rules.RULE_MODULES``, valida ogni
dichiarazione e restituisce le regole ordinate per id. Aggiungere una regola non richiede di
modificare il motore.
"""

from __future__ import annotations

import importlib
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

logger = logging.getLogger(__name__)

RULE_ID_PATTERN = r"^[ABCD]-[A-Z0-9]+(?:-[A-Z0-9]+)*$"
GROUPS: tuple[str, ...] = ("A", "B", "C", "D")
SEVERITIES: tuple[str, ...] = ("P0", "P1", "P2")          # P0 più grave
SCOPE_KINDS: tuple[str, ...] = ("portfolio", "aggregate", "instrument", "user")
RULE_STATUSES: tuple[str, ...] = ("pass", "fail", "skip", "error")
SKIP_CODES: tuple[str, ...] = (
    "empty_portfolio", "no_targets", "scenario_not_available", "truncated_output",
    "no_reference_data", "not_applicable", "aggregate_too_small", "no_transactions",
    "no_history", "feature_disabled",
)
ERROR_CODES: tuple[str, ...] = (
    "exception", "timeout", "tool_error", "invalid_outcome", "deadline_exceeded",
)
FAIL_CODE_DEFAULT = "invariant_violated"
# Aree mostrate all'utente (TASK-81): codice -> etichetta italiana.
AREAS: dict[str, str] = {
    "stress": "Stress test",
    "classification": "Classificazione degli strumenti",
    "rebalance": "Ribilanciamento e PAC",
    "simulation": "Simulazioni",
    "costs": "Costi",
    "income": "Reddito e dividendi",
    "montecarlo": "Proiezioni Monte Carlo",
    "daily": "Variazioni giornaliere",
    "values": "Valori, pesi e liquidità",
    "aggregate": "Vista aggregata",
    "performance": "Rendimenti",
    "doctor": "Metriche del Doctor",
    "data": "Qualità dei dati importati",
}
DEFAULT_RULE_TIMEOUT_S = 30.0
MAX_EVIDENCE_ITEMS = 50

RULES_PACKAGE = "app.services.auditor.rules"
MAX_RULE_TIMEOUT_S = 300.0
KNOWN_DEFECT_PATTERN = r"^TASK-[0-9]+$"

_RULE_ID_RE = re.compile(RULE_ID_PATTERN)
_KNOWN_DEFECT_RE = re.compile(KNOWN_DEFECT_PATTERN)
_REQUIRED_KEYS = ("id", "group", "title", "area", "severity", "findings", "scopes", "tools", "check")
_OPTIONAL_KEYS = ("timeout_s", "known_defect")


@dataclass(frozen=True)
class Rule:
    id: str                       # stabile, RULE_ID_PATTERN, prefisso = group
    group: str                    # "A" | "B" | "C" | "D"
    title: str                    # italiano, per l'utente: niente id, niente gergo
    area: str                     # chiave di AREAS
    severity: str                 # "P0" | "P1" | "P2"
    findings: tuple[str, ...]     # es. ("V365-002",); vuota solo per regole senza finding
    scopes: tuple[str, ...]       # sottoinsieme non vuoto di SCOPE_KINDS
    tools: tuple[str, ...]        # tool (o "ctx.transactions" / "ctx.performance_audit") letti
    check: Callable[[Any, dict[str, Any]], dict[str, Any]]
    timeout_s: float = DEFAULT_RULE_TIMEOUT_S
    known_defect: str | None = None   # "TASK-NN" quando la regola trova un difetto reale aperto


class RuleRegistrationError(ValueError):
    """Dichiarazione non valida, id duplicato, filtro su un id o gruppo sconosciuto."""


def _string_tuple(value: Any, field: str, rule_id: str, *, allow_empty: bool) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise RuleRegistrationError(f"{rule_id}: {field} deve essere una lista di stringhe")
    items = tuple(value)
    if not allow_empty and not items:
        raise RuleRegistrationError(f"{rule_id}: {field} non può essere vuota")
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise RuleRegistrationError(f"{rule_id}: {field} contiene un elemento non valido: {item!r}")
    if len(set(items)) != len(items):
        raise RuleRegistrationError(f"{rule_id}: {field} contiene duplicati")
    return items


def rule_from_declaration(declaration: Mapping[str, Any]) -> Rule:
    """Valida una dichiarazione (§3.2) e la trasforma in ``Rule``."""
    if isinstance(declaration, Rule):
        declaration = {
            "id": declaration.id, "group": declaration.group, "title": declaration.title,
            "area": declaration.area, "severity": declaration.severity,
            "findings": list(declaration.findings), "scopes": list(declaration.scopes),
            "tools": list(declaration.tools), "check": declaration.check,
            "timeout_s": declaration.timeout_s, "known_defect": declaration.known_defect,
        }
    if not isinstance(declaration, Mapping):
        raise RuleRegistrationError(f"dichiarazione non valida: atteso un dict, trovato {type(declaration).__name__}")

    raw_id = declaration.get("id")
    rule_id = raw_id if isinstance(raw_id, str) else repr(raw_id)
    missing = [key for key in _REQUIRED_KEYS if key not in declaration]
    if missing:
        raise RuleRegistrationError(f"{rule_id}: chiavi mancanti: {', '.join(missing)}")
    unknown = sorted(str(k) for k in declaration if k not in _REQUIRED_KEYS and k not in _OPTIONAL_KEYS)
    if unknown:
        raise RuleRegistrationError(f"{rule_id}: chiavi sconosciute: {', '.join(unknown)}")

    if not isinstance(raw_id, str) or not _RULE_ID_RE.match(raw_id):
        raise RuleRegistrationError(f"{rule_id}: id fuori dal pattern {RULE_ID_PATTERN}")
    group = declaration["group"]
    if group not in GROUPS:
        raise RuleRegistrationError(f"{rule_id}: gruppo sconosciuto {group!r}")
    if raw_id.split("-", 1)[0] != group:
        raise RuleRegistrationError(f"{rule_id}: il prefisso dell'id non corrisponde al gruppo {group}")
    title = declaration["title"]
    if not isinstance(title, str) or not title.strip():
        raise RuleRegistrationError(f"{rule_id}: title vuoto")
    area = declaration["area"]
    if area not in AREAS:
        raise RuleRegistrationError(f"{rule_id}: area sconosciuta {area!r}")
    severity = declaration["severity"]
    if severity not in SEVERITIES:
        raise RuleRegistrationError(f"{rule_id}: severità sconosciuta {severity!r}")
    findings = _string_tuple(declaration["findings"], "findings", rule_id, allow_empty=True)
    scopes = _string_tuple(declaration["scopes"], "scopes", rule_id, allow_empty=False)
    bad_scopes = [s for s in scopes if s not in SCOPE_KINDS]
    if bad_scopes:
        raise RuleRegistrationError(f"{rule_id}: scope sconosciuti: {', '.join(bad_scopes)}")
    tools = _string_tuple(declaration["tools"], "tools", rule_id, allow_empty=False)
    check = declaration["check"]
    if not callable(check):
        raise RuleRegistrationError(f"{rule_id}: check non è chiamabile")

    timeout_s = declaration.get("timeout_s", DEFAULT_RULE_TIMEOUT_S)
    if timeout_s is None:
        timeout_s = DEFAULT_RULE_TIMEOUT_S
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s):
        raise RuleRegistrationError(f"{rule_id}: timeout_s non valido")
    if timeout_s <= 0 or timeout_s > MAX_RULE_TIMEOUT_S:
        raise RuleRegistrationError(f"{rule_id}: timeout_s deve essere in (0, {MAX_RULE_TIMEOUT_S:g}]")
    known_defect = declaration.get("known_defect")
    if known_defect is not None and (not isinstance(known_defect, str) or not _KNOWN_DEFECT_RE.match(known_defect)):
        raise RuleRegistrationError(f"{rule_id}: known_defect fuori dal pattern {KNOWN_DEFECT_PATTERN}")

    return Rule(
        id=raw_id, group=group, title=title, area=area, severity=severity, findings=findings,
        scopes=scopes, tools=tools, check=check, timeout_s=float(timeout_s), known_defect=known_defect,
    )


def _module_name(name: str) -> str:
    return name if "." in name else f"{RULES_PACKAGE}.{name}"


def _default_modules() -> tuple[str, ...]:
    from .rules import RULE_MODULES

    return tuple(RULE_MODULES)


def load_rules(modules: Sequence[str] | None = None) -> list[Rule]:
    """Importa i moduli delle regole e restituisce le regole validate, ordinate per id.

    ``modules`` None = ``rules.RULE_MODULES``. Un nome senza punti è relativo al pacchetto
    ``app.services.auditor.rules``; uno con punti è un modulo assoluto (test). Un modulo assente
    è ignorato con un warning; ogni altro errore di import si propaga.
    """
    names = _default_modules() if modules is None else tuple(modules)
    rules: dict[str, Rule] = {}
    for name in names:
        full_name = _module_name(name)
        try:
            module = importlib.import_module(full_name)
        except ModuleNotFoundError as exc:
            if exc.name == full_name:
                logger.warning("Auditor: modulo di regole %s assente, ignorato", full_name)
                continue
            raise
        declarations = getattr(module, "RULES", None)
        if declarations is None:
            raise RuleRegistrationError(f"{full_name}: manca la lista RULES")
        if isinstance(declarations, (str, bytes, Mapping)) or not isinstance(declarations, (list, tuple)):
            raise RuleRegistrationError(f"{full_name}: RULES deve essere una lista di dichiarazioni")
        for declaration in declarations:
            try:
                rule = rule_from_declaration(declaration)
            except RuleRegistrationError as exc:
                raise RuleRegistrationError(f"{full_name}: {exc}") from exc
            if rule.id in rules:
                raise RuleRegistrationError(f"{full_name}: id duplicato {rule.id}")
            rules[rule.id] = rule
    return [rules[rule_id] for rule_id in sorted(rules)]


def select_rules(
    rules: Sequence[Rule], *, groups: Sequence[str] | None = None, rule_ids: Sequence[str] | None = None,
) -> list[Rule]:
    """Filtra per gruppo e per id (in AND). Id o gruppo sconosciuto → ``RuleRegistrationError``."""
    selected = sorted(rules, key=lambda r: r.id)
    if groups:
        unknown_groups = sorted({g for g in groups if g not in GROUPS})
        if unknown_groups:
            raise RuleRegistrationError(f"gruppi sconosciuti: {', '.join(map(str, unknown_groups))}")
        wanted_groups = set(groups)
        selected = [r for r in selected if r.group in wanted_groups]
    if rule_ids:
        known_ids = {r.id for r in rules}
        unknown_ids = sorted({i for i in rule_ids if i not in known_ids}, key=str)
        if unknown_ids:
            raise RuleRegistrationError(f"regole sconosciute: {', '.join(map(str, unknown_ids))}")
        wanted_ids = set(rule_ids)
        selected = [r for r in selected if r.id in wanted_ids]
    return selected
