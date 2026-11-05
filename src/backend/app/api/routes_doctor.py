"""Portfolio Doctor 2.0 REST API: personal policies, evaluation, Scenario Lab.

Contract: docs/doctor2/api-contracts.md §5. Every endpoint is under ``/api``
and authenticated with ``require_auth_rate_limited``; the business logic is
in :class:`app.services.doctor_policy.service.DoctorPolicyService` (shared
with the Copilot tools).

Errors use the app-wide shape ``{"error": {"code", "message", "details"}}``
with ``details = {"field_errors": [...], "request_id": str, "retryable": bool}``:
``invalid_request`` 400, ``validation_error`` 422 (invalid policy on save),
``not_found`` 404 (also a scope the user does not own), ``version_conflict``
409, ``confirmation_invalid`` 409, ``feature_disabled`` 404.

Bodies are read as raw JSON and validated here, so a malformed body is a 400
``invalid_request`` with ``field_errors`` instead of FastAPI's generic 422.
The routes use :class:`DoctorRoute`, so FastAPI's own request validation
(malformed path parameters such as a non-integer ``policy_id``, unreadable
JSON) also answers 400 ``invalid_request`` in the contract shape; the
app-wide 422 handler of the other routes is unchanged.

Must be registered before ``register_portfolio_health_routes`` (main.py).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import APIRouter, Body, Depends, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError

from ..auth import AuthContext
from ..errors import AppError
from ..models import ErrorResponse
from ..rate_limit import require_auth_rate_limited
from ..schemas.doctor_policy import (
    DoctorFeaturesRead,
    MetricsResponse,
    PolicyEvaluationResponse,
    PolicyPreviewResponse,
    PolicyRead,
    PolicyReadEnvelope,
    PolicyVersionsResponse,
    PreviewRequest,
    RestoreRequest,
    SaveRequest,
    TemplatesResponse,
    ValidateRequest,
    ValidateResponse,
)
from ..services.doctor_policy.errors import ConfirmationInvalid, FeatureDisabled, InvalidRequest, error_details
from ..services.doctor_policy.service import DoctorPolicyService

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

_ERRORS = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def request_id_of(request: Request) -> str:
    """Caller's X-Request-ID when well formed, else a fresh uuid4."""
    candidate = request.headers.get("x-request-id") or ""
    if _REQUEST_ID_RE.match(candidate):
        return candidate
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str) and existing:
        return existing
    return uuid.uuid4().hex


def _with_request_id(exc: AppError, request_id: str) -> AppError:
    details = exc.details if isinstance(exc.details, dict) else {}
    merged = error_details(
        field_errors=details.get("field_errors"),
        retryable=bool(details.get("retryable", False)),
        request_id=request_id,
    )
    for key, value in details.items():
        merged.setdefault(key, value)
    exc.details = merged
    return exc


def _pydantic_field_errors(exc: ValidationError) -> list[dict[str, str]]:
    out = []
    for err in exc.errors():
        loc = ""
        for part in err.get("loc", ()):
            loc += f"[{part}]" if isinstance(part, int) else (f".{part}" if loc else str(part))
        out.append({"field": loc or "body", "code": str(err.get("type", "invalid")), "message": str(err.get("msg", ""))})
    return out


_REQUEST_PARTS = ("path", "query", "body", "header", "cookie")
BIGINT_MAX = 9_223_372_036_854_775_807


def _request_field_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    out = []
    for err in exc.errors():
        parts = list(err.get("loc", ()))
        if parts and parts[0] in _REQUEST_PARTS:
            parts = parts[1:]
        loc = ""
        for part in parts:
            loc += f"[{part}]" if isinstance(part, int) else (f".{part}" if loc else str(part))
        out.append({"field": loc or "body", "code": str(err.get("type", "invalid")), "message": str(err.get("msg", ""))})
    return out


class DoctorRoute(APIRoute):
    """Route class of the Doctor endpoints: request-validation errors become
    400 ``invalid_request`` with ``{field_errors, request_id, retryable}``."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        handler = super().get_route_handler()

        async def doctor_route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return JSONResponse(
                    status_code=400,
                    content={"error": {
                        "code": "invalid_request",
                        "message": "Richiesta non valida",
                        "details": error_details(
                            field_errors=_request_field_errors(exc), request_id=request_id_of(request),
                        ),
                    }},
                )

        return doctor_route_handler


def _parse(model: type[M], payload: Any) -> M:
    if not isinstance(payload, dict):
        raise InvalidRequest("Il corpo della richiesta deve essere un oggetto JSON")
    payload = dict(payload)
    # Accept the single-portfolio spelling used by the GET endpoints.
    if "portfolio_ids" not in payload and "portfolio_id" in payload and "portfolio_ids" in model.model_fields:
        payload["portfolio_ids"] = [payload.pop("portfolio_id")]
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise InvalidRequest("Richiesta non valida", field_errors=_pydantic_field_errors(exc)) from exc


def _query_ids(portfolio_ids: list[str], portfolio_id: str | None) -> list[Any]:
    raw = list(portfolio_ids or [])
    if portfolio_id is not None:
        raw.append(portfolio_id)
    ids: list[Any] = []
    for value in raw:
        # Also accept "19,26" in one parameter.
        ids.extend(part for part in str(value).split(",") if part.strip())
    return ids


def register_doctor_routes(
    router: APIRouter,
    repo: Any,
    *,
    settings: Any,
    service: DoctorPolicyService | None = None,
    service_getter: Callable[[], DoctorPolicyService] | None = None,
) -> None:
    """Register ``/doctor/...`` routes.

    ``service_getter`` (or ``service``) supplies the DoctorPolicyService;
    by default one is built on ``repo``. Feature flags are read from
    ``settings`` at request time.
    """
    if service_getter is None:
        _svc = service or DoctorPolicyService(repo)
        service_getter = lambda: _svc  # noqa: E731
    Auth = Depends(require_auth_rate_limited)
    outer_router = router
    # Doctor routes live on their own router (DoctorRoute error shape),
    # included into the caller's router at the end of this function.
    router = APIRouter(route_class=DoctorRoute)
    PolicyId = Path(ge=1, le=BIGINT_MAX, description="Id della policy")

    def policy_enabled() -> None:
        if not getattr(settings, "doctor_policy_enabled", True):
            raise FeatureDisabled("Portfolio Doctor policy disabilitate")

    def simulator_enabled() -> None:
        if not getattr(settings, "doctor_simulator_enabled", True):
            raise FeatureDisabled("Scenario Lab disabilitato")

    def run(request: Request, fn: Callable[[], T], *guards: Callable[[], None]) -> T:
        rid = request_id_of(request)
        try:
            for guard in guards:
                guard()
            return fn()
        except AppError as exc:
            raise _with_request_id(exc, rid) from None

    IdsQuery = Query(default_factory=list, description="Portafogli dello scope (parametro ripetuto)")
    IdQuery = Query(default=None, description="Portafoglio singolo (alternativa a portfolio_ids)")

    @router.get("/doctor/features", response_model=DoctorFeaturesRead)
    def get_doctor_features(_auth: AuthContext = Auth) -> DoctorFeaturesRead:
        return DoctorPolicyService.features(settings)

    @router.get("/doctor/metrics", response_model=MetricsResponse, responses=_ERRORS)
    def get_doctor_metrics(request: Request, _auth: AuthContext = Auth) -> MetricsResponse:
        return run(request, DoctorPolicyService.metrics_registry, policy_enabled)

    @router.get("/doctor/templates", response_model=TemplatesResponse, responses=_ERRORS)
    def get_doctor_templates(request: Request, _auth: AuthContext = Auth) -> TemplatesResponse:
        return run(request, DoctorPolicyService.templates, policy_enabled)

    @router.get("/doctor/policies", response_model=PolicyReadEnvelope, responses=_ERRORS)
    def get_doctor_policy(
        request: Request,
        portfolio_ids: list[str] = IdsQuery,
        portfolio_id: str | None = IdQuery,
        _auth: AuthContext = Auth,
    ) -> PolicyReadEnvelope:
        ids = _query_ids(portfolio_ids, portfolio_id)
        return run(
            request,
            lambda: PolicyReadEnvelope(policy=service_getter().get_policy(_auth.user_id, ids)),
            policy_enabled,
        )

    @router.post("/doctor/policies/validate", response_model=ValidateResponse, responses=_ERRORS)
    def validate_doctor_policy(
        request: Request, payload: Any = Body(default=None), _auth: AuthContext = Auth,
    ) -> ValidateResponse:
        def do() -> ValidateResponse:
            body = _parse(ValidateRequest, payload)
            return service_getter().validate(_auth.user_id, body.portfolio_ids, body.document)

        return run(request, do, policy_enabled)

    @router.post("/doctor/policies/preview", response_model=PolicyPreviewResponse, responses=_ERRORS)
    def preview_doctor_policy(
        request: Request, payload: Any = Body(default=None), _auth: AuthContext = Auth,
    ) -> PolicyPreviewResponse:
        def do() -> PolicyPreviewResponse:
            body = _parse(PreviewRequest, payload)
            return service_getter().preview(
                _auth.user_id, body.portfolio_ids, body.document, base_version=body.base_version, source=body.source,
            )

        return run(request, do, policy_enabled)

    @router.post("/doctor/policies", response_model=PolicyRead, status_code=201, responses=_ERRORS)
    def save_doctor_policy(
        request: Request, payload: Any = Body(default=None), _auth: AuthContext = Auth,
    ) -> PolicyRead:
        def do() -> PolicyRead:
            if isinstance(payload, dict) and not payload.get("confirmation_token"):
                raise ConfirmationInvalid("Conferma mancante: genera l'anteprima e conferma il salvataggio")
            body = _parse(SaveRequest, payload)
            return service_getter().save(
                _auth.user_id,
                body.portfolio_ids,
                name=body.name,
                document=body.document,
                base_version=body.base_version,
                confirmation_token=body.confirmation_token,
            )

        return run(request, do, policy_enabled)

    @router.get("/doctor/policies/{policy_id}/versions", response_model=PolicyVersionsResponse, responses=_ERRORS)
    def list_doctor_policy_versions(
        request: Request, policy_id: int = PolicyId, _auth: AuthContext = Auth,
    ) -> PolicyVersionsResponse:
        return run(request, lambda: service_getter().list_versions(_auth.user_id, policy_id), policy_enabled)

    @router.post("/doctor/policies/{policy_id}/restore", response_model=PolicyRead, responses=_ERRORS)
    def restore_doctor_policy(
        request: Request, policy_id: int = PolicyId, payload: Any = Body(default=None), _auth: AuthContext = Auth,
    ) -> PolicyRead:
        def do() -> PolicyRead:
            body = _parse(RestoreRequest, payload)
            return service_getter().restore(
                _auth.user_id, policy_id, version_number=body.version_number, base_version=body.base_version,
            )

        return run(request, do, policy_enabled)

    @router.get("/doctor/evaluation", response_model=PolicyEvaluationResponse, responses=_ERRORS)
    def get_doctor_evaluation(
        request: Request,
        portfolio_ids: list[str] = IdsQuery,
        portfolio_id: str | None = IdQuery,
        _auth: AuthContext = Auth,
    ) -> PolicyEvaluationResponse:
        ids = _query_ids(portfolio_ids, portfolio_id)
        return run(request, lambda: service_getter().evaluate(_auth.user_id, ids), policy_enabled)

    # --- Scenario Lab (logic in app/services/doctor_policy/scenario.py) -------

    @router.post("/doctor/scenarios/preview", responses={**_ERRORS, 501: {"model": ErrorResponse}})
    def preview_doctor_scenario(
        request: Request, payload: Any = Body(default=None), _auth: AuthContext = Auth,
    ) -> Any:
        def do() -> Any:
            if not isinstance(payload, dict):
                raise InvalidRequest("Il corpo della richiesta deve essere un oggetto JSON")
            return service_getter().preview_scenario(_auth.user_id, payload)

        return _jsonable(run(request, do, simulator_enabled))

    @router.post("/doctor/scenarios/compare", responses={**_ERRORS, 501: {"model": ErrorResponse}})
    def compare_doctor_scenarios(
        request: Request, payload: Any = Body(default=None), _auth: AuthContext = Auth,
    ) -> Any:
        def do() -> Any:
            if not isinstance(payload, dict):
                raise InvalidRequest("Il corpo della richiesta deve essere un oggetto JSON")
            return service_getter().compare_scenarios(_auth.user_id, payload)

        return _jsonable(run(request, do, simulator_enabled))

    outer_router.include_router(router)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return JSONResponse(content=value.model_dump(mode="json"))
    return value
