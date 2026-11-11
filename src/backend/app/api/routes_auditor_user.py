"""Esiti dei controlli notturni sui portafogli dell'utente (TASK-81, docs/auditor/architecture.md §6.1, §7.3).

GET /api/doctor/auditor/summary?portfolio_id=N  oppure  ?portfolio_ids=1,2,3 (anche ripetuto)
    200 {available, run_finished_at, checks_passed, checks_in_review,
         areas: [{area, label, status, checks: [{title, status}]}]}

Sola lettura, ``require_auth`` (con il limite per utente del Doctor) e proprietà di **ogni**
portafoglio dello scope verificata come nel Doctor (``resolve_portfolio_scope``): un portafoglio
altrui è 404 ``not_found``, uno scope vuoto o malformato 400 ``invalid_request``.

Regole del calcolo:

- si leggono le righe dell'ultima corsa **conclusa** (``AuditorStore.latest_results_for_portfolios``);
  per una vista aggregata l'unione delle righe dei portafogli che la compongono;
- per ogni regola l'esito peggiore (``fail`` > ``error`` > ``skip`` > ``pass``); ``pass`` →
  ``passed``, ``fail`` → ``in_review``; ``error`` e ``skip`` non sono mostrati né contati;
- ``available: false`` (e nient'altro) se non c'è una corsa conclusa, se è finita da più di 48 ore
  o se nessun controllo è mostrabile per lo scope;
- titoli e aree dal registro delle regole (``load_rules()``); una regola non più nel registro non è
  mostrata. Mai id di regole, severità, evidenze, valori o id della corsa.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Iterable, Sequence

from fastapi import APIRouter, Depends, Query

from ..auth import AuthContext
from ..errors import AppError
from ..rate_limit import require_auth_rate_limited
from ..repository._scope import NOT_FOUND_MESSAGE
from ..services.auditor.registry import AREAS, Rule, load_rules
from ..services.doctor_policy.scope import ScopeError, normalize_scope_ids

logger = logging.getLogger(__name__)

SUMMARY_PATH = "/doctor/auditor/summary"
MAX_RUN_AGE = timedelta(hours=48)
# Esito peggiore per primo (§7.2).
STATUS_RANK = {"fail": 3, "error": 2, "skip": 1, "pass": 0}
USER_STATUS = {"pass": "passed", "fail": "in_review"}
AREA_ORDER = {code: index for index, code in enumerate(AREAS)}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def unavailable() -> dict[str, Any]:
    return {"available": False, "run_finished_at": None, "checks_passed": 0, "checks_in_review": 0, "areas": []}


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def worst_status_by_rule(rows: Iterable[dict]) -> dict[str, str]:
    """rule_id -> esito peggiore fra le righe (tutti i portafogli e i tipi di scope)."""
    worst: dict[str, str] = {}
    for row in rows:
        status = str(row.get("status"))
        if status not in STATUS_RANK:
            continue
        rule_id = str(row.get("rule_id"))
        current = worst.get(rule_id)
        if current is None or STATUS_RANK[status] > STATUS_RANK[current]:
            worst[rule_id] = status
    return worst


def build_summary(result: dict, rules: Sequence[Rule], *, now: datetime) -> dict[str, Any]:
    """Payload utente da ``latest_results_for_portfolios`` e dal registro delle regole."""
    run = result.get("run") if isinstance(result, dict) else None
    if not run:
        return unavailable()
    finished = _parse_dt(run.get("finished_at"))
    if finished is None or now - finished > MAX_RUN_AGE or finished - now > MAX_RUN_AGE:
        return unavailable()

    by_id = {rule.id: rule for rule in rules}
    areas: dict[str, list[dict[str, str]]] = {}
    for rule_id, status in worst_status_by_rule(result.get("rows") or []).items():
        rule = by_id.get(rule_id)
        user_status = USER_STATUS.get(status)
        if rule is None or user_status is None or rule.area not in AREAS:
            continue
        areas.setdefault(rule.area, []).append({"title": rule.title, "status": user_status})

    if not areas:
        return unavailable()
    out_areas = []
    passed = in_review = 0
    for code in sorted(areas, key=lambda c: AREA_ORDER[c]):
        # In verifica prima, poi per titolo; titoli uguali (due regole) restano due righe.
        checks = sorted(areas[code], key=lambda c: (c["status"] != "in_review", c["title"].casefold()))
        area_in_review = any(c["status"] == "in_review" for c in checks)
        passed += sum(1 for c in checks if c["status"] == "passed")
        in_review += sum(1 for c in checks if c["status"] == "in_review")
        out_areas.append({
            "area": code,
            "label": AREAS[code],
            "status": "in_review" if area_in_review else "passed",
            "checks": checks,
        })
    out_areas.sort(key=lambda a: (a["status"] != "in_review", AREA_ORDER[a["area"]]))
    return {
        "available": True,
        "run_finished_at": finished.astimezone(UTC).isoformat(),
        "checks_passed": passed,
        "checks_in_review": in_review,
        "areas": out_areas,
    }


def _query_ids(portfolio_ids: list[str], portfolio_id: str | None) -> list[str]:
    raw = list(portfolio_ids or [])
    if portfolio_id is not None:
        raw.append(portfolio_id)
    ids: list[str] = []
    for value in raw:
        ids.extend(part for part in str(value).split(",") if part.strip())
    return ids


def _invalid(message: str) -> AppError:
    return AppError(code="invalid_request", message=message, status_code=400)


def resolve_owned_scope(repo: Any, raw_ids: list[str], user_id: str) -> list[int]:
    """Come ``DoctorPolicyService.resolve_scope``: 1..20 id, tutti dell'utente, stessa valuta base."""
    try:
        ids = normalize_scope_ids(raw_ids)
    except ScopeError as exc:
        raise _invalid(str(exc)) from None
    try:
        repo.resolve_portfolio_scope(ids, user_id)
    except ValueError as exc:
        if str(exc) == NOT_FOUND_MESSAGE:
            raise AppError(code="not_found", message=NOT_FOUND_MESSAGE, status_code=404) from None
        raise _invalid(str(exc)) from None
    return ids


def register_auditor_user_routes(
    router: APIRouter,
    repo: Any,
    *,
    store_getter: Callable[[], Any],
    rules_loader: Callable[[], Sequence[Rule]] = load_rules,
    now: Callable[[], datetime] | None = None,
) -> None:
    cache: dict[str, list[Rule]] = {}

    def rules() -> list[Rule]:
        # Titoli e aree non cambiano a processo vivo: il registro si carica una volta.
        if "rules" not in cache:
            cache["rules"] = list(rules_loader())
        return cache["rules"]

    @router.get(SUMMARY_PATH)
    def get_auditor_summary(
        portfolio_ids: list[str] = Query(default_factory=list, description="Portafogli dello scope"),
        portfolio_id: str | None = Query(default=None, description="Portafoglio singolo"),
        auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> dict[str, Any]:
        """Controlli notturni sui portafogli dello scope: titoli per area ed esito, nessun dettaglio."""
        ids = resolve_owned_scope(repo, _query_ids(portfolio_ids, portfolio_id), auth.user_id)
        try:
            result = store_getter().latest_results_for_portfolios(ids)
            registry = rules()
        except Exception as exc:  # l'indicatore è accessorio: mai un errore nel Doctor
            logger.warning("auditor user summary unavailable (%s)", type(exc).__name__)
            return unavailable()
        return build_summary(result, registry, now=(now or _utcnow)())
