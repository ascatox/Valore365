"""DoctorPolicyService: orchestration of Doctor 2.0 policies (contract §5).

Used by the REST routes (``app/api/routes_doctor.py``) and by the Copilot
tools. Every public method:

1. normalizes the scope (sorted, deduplicated, 1..20 ids) and checks through
   ``repo.resolve_portfolio_scope`` that the user owns *every* portfolio and
   that they share one base currency. A policy reached by id is authorized
   the same way on its stored members, so an aggregate policy whose
   portfolio was deleted or is no longer owned is unreadable (404);
2. never writes to transactions/positions; the only writes are the policy
   tables and confirmation tokens;
3. raises :mod:`.errors` exceptions (``AppError`` subclasses) with the
   contract codes.

Saving needs the one-shot confirmation token issued by :meth:`preview`
(Copilot only ever previews: it never calls :meth:`save` or :meth:`restore`).
Logs carry counts and latencies only: no amounts, weights or tokens.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from ...repository._scope import NOT_FOUND_MESSAGE
from ...schemas.doctor_policy import (
    DoctorFeaturesRead,
    MetricDefinitionRead,
    MetricsResponse,
    PolicyDiffItem,
    PolicyDocument,
    PolicyEvaluationResponse,
    PolicyPreviewResponse,
    PolicyRead,
    PolicyVersionRead,
    PolicyVersionsResponse,
    TemplateRead,
    TemplatesResponse,
    ValidateResponse,
)
from .cache import TTLCache
from .confirmation import TOKEN_SOURCES, consume_token, issue_token
from .errors import (
    ConfirmationInvalid,
    InvalidRequest,
    NotFound,
    PolicyValidationFailed,
    VersionConflict,
)
from .evaluator import build_evaluation_response
from .metrics import METHODOLOGY_VERSION, compute_metrics, metric_definitions
from .scope import ScopeError, build_scope, normalize_scope_ids
from .snapshot import build_snapshot
from .store import DoctorPolicyStore, PolicySetRecord, StoreVersionConflict
from .templates import TEMPLATE_VERSION, list_templates
from .validator import diff_documents, document_hash, validate_and_normalize

logger = logging.getLogger("valore365.doctor_policy")

EVALUATION_CACHE_TTL_SECONDS = 60.0
EVALUATION_CACHE_MAX_ENTRIES = 512
DEFAULT_POLICY_NAME = "La mia policy"
MAX_NAME_LENGTH = 80


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _field_errors(errors: Iterable[Any]) -> list[dict[str, Any]]:
    out = []
    for e in errors:
        out.append(e.model_dump() if hasattr(e, "model_dump") else dict(e))
    return out


class DoctorPolicyService:
    def __init__(
        self,
        repo: Any,
        *,
        store: DoctorPolicyStore | None = None,
        cache: TTLCache | None = None,
    ) -> None:
        self.repo = repo
        self._store = store
        self.cache = cache or TTLCache(
            ttl_seconds=EVALUATION_CACHE_TTL_SECONDS, max_entries=EVALUATION_CACHE_MAX_ENTRIES,
        )

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------

    @property
    def store(self) -> DoctorPolicyStore:
        # Built on demand: ``repo`` may be a lazy proxy whose engine changes in tests.
        return self._store if self._store is not None else DoctorPolicyStore(self.repo.engine)

    def resolve_scope(self, portfolio_ids: Iterable[Any] | None, user_id: str) -> list[int]:
        """Sorted unique ids the user owns (same base currency, 1..20).

        Raises InvalidRequest (400) for an empty/too long/malformed list or
        mixed currencies, NotFound (404) when any portfolio is not the user's.
        """
        try:
            ids = normalize_scope_ids(list(portfolio_ids or []))
        except ScopeError as exc:
            raise InvalidRequest(str(exc)) from exc
        try:
            self.repo.resolve_portfolio_scope(ids, user_id)
        except ValueError as exc:
            if str(exc) == NOT_FOUND_MESSAGE:
                raise NotFound(NOT_FOUND_MESSAGE) from exc
            raise InvalidRequest(str(exc)) from exc
        return ids

    def _authorized_record(self, user_id: str, policy_id: int) -> PolicySetRecord:
        """Policy set by id, readable only if every member is still the user's."""
        record = self.store.get_policy_set_by_id(user_id, int(policy_id))
        if record is None or not record.portfolio_ids:
            raise NotFound("Policy non trovata")
        try:
            self.resolve_scope(record.portfolio_ids, user_id)
        except (NotFound, InvalidRequest) as exc:
            # A deleted / no longer owned member: the policy is not readable.
            raise NotFound("Policy non trovata") from exc
        return record

    @staticmethod
    def _policy_read(record: PolicySetRecord) -> PolicyRead:
        return PolicyRead(
            id=record.id,
            name=record.name,
            scope=build_scope(record.portfolio_ids),
            active=record.active,
            current_version=record.current_version,
            document=PolicyDocument.model_validate(record.document or {"schema_version": 1, "rules": []}),
            updated_at=_iso(record.updated_at) or "",
            created_at=_iso(record.created_at) or "",
        )

    def _snapshot_and_metrics(self, ids: list[int], user_id: str):
        try:
            snapshot = build_snapshot(self.repo, ids, user_id)
        except ScopeError as exc:
            raise InvalidRequest(str(exc)) from exc
        except ValueError as exc:
            if str(exc) == NOT_FOUND_MESSAGE:
                raise NotFound(NOT_FOUND_MESSAGE) from exc
            raise InvalidRequest(str(exc)) from exc
        return snapshot, compute_metrics(snapshot, self.repo)

    # ------------------------------------------------------------------
    # static data
    # ------------------------------------------------------------------

    @staticmethod
    def features(settings: Any) -> DoctorFeaturesRead:
        return DoctorFeaturesRead(
            policy_enabled=bool(getattr(settings, "doctor_policy_enabled", True)),
            simulator_enabled=bool(getattr(settings, "doctor_simulator_enabled", True)),
        )

    @staticmethod
    def metrics_registry() -> MetricsResponse:
        return MetricsResponse(
            methodology_version=METHODOLOGY_VERSION,
            metrics=[MetricDefinitionRead(**d) for d in metric_definitions()],
        )

    @staticmethod
    def templates() -> TemplatesResponse:
        return TemplatesResponse(
            template_version=TEMPLATE_VERSION,
            templates=[TemplateRead(**t) for t in list_templates()],
        )

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------

    def get_policy(self, user_id: str, portfolio_ids: Iterable[Any]) -> PolicyRead | None:
        """Active policy of the exact scope, or None."""
        ids = self.resolve_scope(portfolio_ids, user_id)
        record = self.store.get_policy_set(user_id, build_scope(ids).fingerprint)
        return self._policy_read(record) if record else None

    def list_versions(self, user_id: str, policy_id: int) -> PolicyVersionsResponse:
        record = self._authorized_record(user_id, policy_id)
        versions = self.store.list_versions(record.id)
        return PolicyVersionsResponse(
            policy_id=record.id,
            current_version=record.current_version,
            versions=[
                PolicyVersionRead(
                    version_number=v.version_number,
                    schema_version=v.schema_version,
                    document=PolicyDocument.model_validate(v.document),
                    document_hash=v.document_hash,
                    source=v.source,
                    diff=[PolicyDiffItem(**d) for d in (v.diff or [])],
                    confirmed_at=_iso(v.confirmed_at) or "",
                    actor=v.actor_user_id,
                )
                for v in versions
            ],
        )

    def evaluate(self, user_id: str, portfolio_ids: Iterable[Any]) -> PolicyEvaluationResponse:
        """Evaluation of the scope's current policy (``no_policy`` if none).

        Cached ~60 s per (user, fingerprint, policy_version, snapshot_id,
        methodology_version): the snapshot is rebuilt every time, so new
        prices/positions change ``snapshot_id`` and miss the cache.
        """
        started = time.monotonic()
        ids = self.resolve_scope(portfolio_ids, user_id)
        fingerprint = build_scope(ids).fingerprint
        record = self.store.get_policy_set(user_id, fingerprint)
        try:
            snapshot = build_snapshot(self.repo, ids, user_id)
        except ScopeError as exc:
            raise InvalidRequest(str(exc)) from exc
        except ValueError as exc:
            if str(exc) == NOT_FOUND_MESSAGE:
                raise NotFound(NOT_FOUND_MESSAGE) from exc
            raise InvalidRequest(str(exc)) from exc
        version = record.current_version if record else 0
        key = (user_id, fingerprint, version, snapshot.snapshot_id, METHODOLOGY_VERSION)
        cached = self.cache.get(key)
        if cached is not None:
            logger.info("doctor.evaluate scope_size=%d cached=1 ms=%.0f", len(ids), (time.monotonic() - started) * 1000)
            return cached.model_copy(deep=True)
        response = build_evaluation_response(
            record.document if record else None,
            snapshot,
            repo=self.repo,
            policy_id=record.id if record else None,
            policy_version=record.current_version if record else None,
            policy_name=record.name if record else None,
        )
        self.cache.set(key, response.model_copy(deep=True))
        logger.info(
            "doctor.evaluate scope_size=%d rules=%d cached=0 ms=%.0f",
            len(ids), len(response.results), (time.monotonic() - started) * 1000,
        )
        return response

    # ------------------------------------------------------------------
    # drafts
    # ------------------------------------------------------------------

    def validate(self, user_id: str, portfolio_ids: Iterable[Any], document: Any) -> ValidateResponse:
        self.resolve_scope(portfolio_ids, user_id)
        normalized, errors = validate_and_normalize(document)
        return ValidateResponse(
            valid=not errors,
            field_errors=errors,
            normalized_document=PolicyDocument.model_validate(normalized) if not errors and normalized else None,
        )

    def preview(
        self,
        user_id: str,
        portfolio_ids: Iterable[Any],
        document: Any,
        *,
        base_version: int | None = None,
        source: str = "manual",
    ) -> PolicyPreviewResponse:
        """Before/after evaluation of a draft on the same snapshot + diff.

        A valid draft also gets a one-shot confirmation token bound to
        (user, scope, document hash, base_version), 15 minutes TTL. The token
        is the only thing that lets :meth:`save` persist the draft.
        """
        started = time.monotonic()
        if source not in TOKEN_SOURCES:
            raise InvalidRequest("source non valida", field_errors=[
                {"field": "source", "code": "invalid", "message": "Valori ammessi: manual, copilot, template"},
            ])
        ids = self.resolve_scope(portfolio_ids, user_id)
        fingerprint = build_scope(ids).fingerprint
        normalized, errors = validate_and_normalize(document)
        valid = not errors and normalized is not None
        record = self.store.get_policy_set(user_id, fingerprint)
        snapshot, metrics = self._snapshot_and_metrics(ids, user_id)

        evaluation_before = None
        if record is not None:
            evaluation_before = build_evaluation_response(
                record.document, snapshot, metrics, repo=self.repo,
                policy_id=record.id, policy_version=record.current_version, policy_name=record.name,
            )
        evaluation_after = None
        diff: list[dict[str, Any]] = []
        token = None
        expires_at = None
        doc_hash = document_hash(normalized if valid else document)
        if valid:
            evaluation_after = build_evaluation_response(
                normalized, snapshot, metrics, repo=self.repo,
                policy_id=record.id if record else None,
                policy_version=None,
                policy_name=record.name if record else None,
            )
            diff = diff_documents(record.document if record else None, normalized)
            issued = issue_token(
                self.repo.engine,
                user_id=user_id,
                scope_fingerprint=fingerprint,
                document_hash=doc_hash,
                base_version=base_version,
                source=source,
            )
            token, expires_at = issued.token, issued.expires_at.isoformat()
        logger.info(
            "doctor.preview scope_size=%d valid=%d errors=%d diff=%d ms=%.0f",
            len(ids), int(valid), len(errors), len(diff), (time.monotonic() - started) * 1000,
        )
        return PolicyPreviewResponse(
            valid=valid,
            field_errors=errors,
            normalized_document=PolicyDocument.model_validate(normalized) if valid else None,
            diff=[PolicyDiffItem(**d) for d in diff],
            evaluation_before=evaluation_before,
            evaluation_after=evaluation_after,
            confirmation_token=token,
            expires_at=expires_at,
            base_version=base_version,
            document_hash=doc_hash,
        )

    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------

    def save(
        self,
        user_id: str,
        portfolio_ids: Iterable[Any],
        *,
        name: str | None,
        document: Any,
        base_version: int | None,
        confirmation_token: str | None,
    ) -> PolicyRead:
        """Persist a previewed draft as a new version (REST only, never Copilot).

        Raises PolicyValidationFailed (422) for an invalid document,
        ConfirmationInvalid (409) when the token is missing, expired, already
        used or issued for another user/scope/document/base_version, and
        VersionConflict (409) when ``base_version`` is not the current
        version. The token is consumed in the same transaction as the save:
        a failed save leaves it unused.
        """
        started = time.monotonic()
        ids = self.resolve_scope(portfolio_ids, user_id)
        scope = build_scope(ids)
        normalized, errors = validate_and_normalize(document)
        if errors or normalized is None:
            raise PolicyValidationFailed("La policy non è valida", field_errors=_field_errors(errors))
        clean_name = (name or "").strip()[:MAX_NAME_LENGTH] or None
        doc_hash = document_hash(normalized)
        store = self.store
        current = store.get_policy_set(user_id, scope.fingerprint)
        previous = current.document if current is not None else None
        try:
            with store.transaction() as conn:
                consumed = consume_token(
                    conn,
                    token=confirmation_token,
                    user_id=user_id,
                    scope_fingerprint=scope.fingerprint,
                    document_hash=doc_hash,
                    base_version=base_version,
                )
                if consumed is None:
                    raise ConfirmationInvalid(
                        "Conferma non valida o scaduta: rigenera l'anteprima e conferma di nuovo",
                    )
                record = store.save_version(
                    owner_user_id=user_id,
                    scope_type=scope.scope_type,
                    scope_fingerprint=scope.fingerprint,
                    portfolio_ids=ids,
                    name=clean_name or (None if current is not None else DEFAULT_POLICY_NAME),
                    document=normalized,
                    document_hash=doc_hash,
                    schema_version=int(normalized.get("schema_version", 1)),
                    source=consumed.source,
                    base_version=base_version,
                    diff=diff_documents(previous, normalized),
                    conn=conn,
                )
        except StoreVersionConflict as exc:
            raise self._conflict(exc) from exc
        self.cache.invalidate_scope(user_id, scope.fingerprint)
        logger.info(
            "doctor.save scope_size=%d version=%d rules=%d ms=%.0f",
            len(ids), record.current_version, len(normalized.get("rules", [])), (time.monotonic() - started) * 1000,
        )
        return self._policy_read(record)

    def restore(self, user_id: str, policy_id: int, *, version_number: int, base_version: int | None) -> PolicyRead:
        """New version copying the document of ``version_number`` (source ``restore``)."""
        record = self._authorized_record(user_id, policy_id)
        store = self.store
        version = store.get_version(record.id, int(version_number))
        if version is None:
            raise NotFound("Versione non trovata")
        normalized, errors = validate_and_normalize(version.document)
        if errors or normalized is None:
            raise PolicyValidationFailed(
                "La versione non è più valida con lo schema corrente", field_errors=_field_errors(errors),
            )
        scope = build_scope(record.portfolio_ids)
        try:
            restored = store.save_version(
                owner_user_id=user_id,
                scope_type=scope.scope_type,
                scope_fingerprint=scope.fingerprint,
                portfolio_ids=record.portfolio_ids,
                name=None,
                document=normalized,
                document_hash=document_hash(normalized),
                schema_version=int(normalized.get("schema_version", 1)),
                source="restore",
                base_version=base_version,
                diff=diff_documents(record.document, normalized),
            )
        except StoreVersionConflict as exc:
            raise self._conflict(exc) from exc
        self.cache.invalidate_scope(user_id, scope.fingerprint)
        logger.info("doctor.restore scope_size=%d version=%d", len(scope.portfolio_ids), restored.current_version)
        return self._policy_read(restored)

    @staticmethod
    def _conflict(exc: StoreVersionConflict) -> VersionConflict:
        err = VersionConflict(
            "La policy è stata modificata nel frattempo: ricarica e riprova",
        )
        err.details["current_version"] = exc.current_version
        return err

    # ------------------------------------------------------------------
    # Scenario Lab (filled by app/services/doctor_policy/scenario.py)
    # ------------------------------------------------------------------

    def _scenario_context(self, user_id: str, portfolio_ids: Iterable[Any], policy_version: int | None):
        """Authorized scope, current policy and ONE snapshot for the Lab (read-only)."""
        ids = self.resolve_scope(portfolio_ids, user_id)
        fingerprint = build_scope(ids).fingerprint
        record = self.store.get_policy_set(user_id, fingerprint)
        current_version = record.current_version if record else None
        if policy_version is not None and policy_version != (current_version or 0):
            err = VersionConflict("La policy è stata modificata nel frattempo: ricarica e riprova")
            err.details["current_version"] = current_version
            raise err
        try:
            snapshot = build_snapshot(self.repo, ids, user_id)
        except ScopeError as exc:
            raise InvalidRequest(str(exc)) from exc
        except ValueError as exc:
            if str(exc) == NOT_FOUND_MESSAGE:
                raise NotFound(NOT_FOUND_MESSAGE) from exc
            raise InvalidRequest(str(exc)) from exc
        meta = {
            "policy_id": record.id if record else None,
            "policy_version": current_version,
            "policy_name": record.name if record else None,
        }
        return ids, fingerprint, record, snapshot, meta

    def preview_scenario(self, user_id: str, payload: dict[str, Any]) -> Any:
        """One Scenario Lab simulation (contract §8). Never writes.

        Cached per (user, fingerprint, policy_version, snapshot_id,
        methodology_version, "scenario", input hash).
        """
        from . import scenario as lab

        started = time.monotonic()
        request = lab.parse_scenario_request(payload)
        ids, fingerprint, record, snapshot, meta = self._scenario_context(
            user_id, request.portfolio_ids, request.policy_version,
        )
        lab._check_snapshot(snapshot, request.snapshot_id)
        key = (
            user_id, fingerprint, meta["policy_version"] or 0, snapshot.snapshot_id, METHODOLOGY_VERSION,
            "scenario", lab.scenario_input_hash(request),
        )
        cached = self.cache.get(key)
        if cached is None:
            cached = lab.preview_scenario(
                snapshot, request, policy_document=record.document if record else None, repo=self.repo, **meta,
            )
            self.cache.set(key, cached.model_copy(deep=True))
        logger.info(
            "doctor.scenario.preview scope_size=%d mode=%s feasible=%d ms=%.0f",
            len(ids), request.mode, int(cached.feasible), (time.monotonic() - started) * 1000,
        )
        return cached.model_copy(deep=True)

    def compare_scenarios(self, user_id: str, payload: dict[str, Any]) -> Any:
        """2–3 scenarios on one snapshot + the current state (contract §8). Never writes."""
        from . import scenario as lab

        started = time.monotonic()
        request = lab.parse_compare_request(payload)
        ids, fingerprint, record, snapshot, meta = self._scenario_context(
            user_id, request.portfolio_ids, request.policy_version,
        )
        lab._check_snapshot(snapshot, request.snapshot_id)
        key = (
            user_id, fingerprint, meta["policy_version"] or 0, snapshot.snapshot_id, METHODOLOGY_VERSION,
            "scenario-compare", tuple(lab.scenario_input_hash(s) for s in request.scenarios),
        )
        cached = self.cache.get(key)
        if cached is None:
            cached = lab.compare_scenarios(
                snapshot, request.scenarios, policy_document=record.document if record else None,
                repo=self.repo, expected_snapshot_id=request.snapshot_id, **meta,
            )
            self.cache.set(key, cached.model_copy(deep=True))
        logger.info(
            "doctor.scenario.compare scope_size=%d scenarios=%d ms=%.0f",
            len(ids), len(request.scenarios), (time.monotonic() - started) * 1000,
        )
        return cached.model_copy(deep=True)


_default_lock = threading.Lock()
_default_service: DoctorPolicyService | None = None


def get_doctor_policy_service(repo: Any) -> DoctorPolicyService:
    """Process-wide service (shared evaluation cache) for REST and Copilot.

    The first call fixes the repository; later calls return the same
    instance so a save from REST invalidates what Copilot reads.
    """
    global _default_service
    with _default_lock:
        if _default_service is None:
            _default_service = DoctorPolicyService(repo)
        return _default_service
