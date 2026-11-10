"""Tribunale del portafoglio REST/SSE API (TASK-65).

Contratto: ``docs/tribunale/api-contracts.md`` §2 (scope e feature flag), §3 (endpoint ed
errori), §9 (eventi SSE). La logica è in
:class:`app.services.tribunal.orchestrator.TribunalOrchestrator`.

- ``GET  /doctor/tribunal/status``          → ``TribunalStatus``
- ``POST /doctor/tribunal/sessions``        → ``text/event-stream`` (o errore JSON prima dello stream)
- ``GET  /doctor/tribunal/sessions/latest`` → ``TribunalLatestResponse``

Tutte le route usano ``DoctorRoute`` (errori di validazione → 400 ``invalid_request``) e
``require_auth_rate_limited``; con ``DOCTOR_TRIBUNAL_ENABLED=false`` rispondono 404
``feature_disabled``. Registrata in ``main.py`` dopo ``register_doctor_routes`` e prima di
``register_portfolio_health_routes``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from ..auth import AuthContext
from ..errors import AppError
from ..models import ErrorResponse
from ..rate_limit import require_auth_rate_limited
from ..services.doctor_policy.errors import FeatureDisabled
from ..services.tribunal.orchestrator import TribunalOrchestrator
from .routes_doctor import DoctorRoute, _parse, _query_ids, _with_request_id, request_id_of

_ERRORS = {code: {"model": ErrorResponse} for code in (400, 404, 409, 429, 503)}


class TribunalStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_ids: list[int] = Field(min_length=1)
    force_new: StrictBool = False


def register_tribunal_routes(
    router: APIRouter,
    repo: Any,
    *,
    settings: Any,
    orchestrator_getter: Callable[[], TribunalOrchestrator] | None = None,
    service_getter: Callable[[], Any] | None = None,
    finance_client: Any = None,
    justetf_client: Any = None,
) -> None:
    """Registra ``/doctor/tribunal/...``.

    ``orchestrator_getter`` fornisce l'orchestratore (i test passano un finto LLM); di
    default se ne crea uno solo, alla prima richiesta, su ``repo``/``settings`` con il
    servizio del Doctor di ``service_getter`` e i client per l'X-Ray. Il flag
    ``doctor_tribunal_enabled`` è letto a ogni richiesta.
    """
    if orchestrator_getter is None:
        holder: dict[str, TribunalOrchestrator] = {}
        holder_lock = threading.Lock()

        def orchestrator_getter() -> TribunalOrchestrator:
            with holder_lock:
                if "o" not in holder:
                    holder["o"] = TribunalOrchestrator(
                        repo, settings, service_getter=service_getter,
                        finance_client=finance_client, justetf_client=justetf_client,
                    )
                return holder["o"]

    getter = orchestrator_getter
    Auth = Depends(require_auth_rate_limited)
    IdsQuery = Query(default_factory=list, description="Portafogli dello scope (parametro ripetuto)")
    IdQuery = Query(default=None, description="Portafoglio singolo (alternativa a portfolio_ids)")

    def add(method: str, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        router.add_api_route(path, endpoint, methods=[method], route_class_override=DoctorRoute,
                             responses=_ERRORS, **kwargs)

    def enabled() -> None:
        if not getattr(settings, "doctor_tribunal_enabled", True):
            raise FeatureDisabled("Tribunale del portafoglio disabilitato")

    def run(request: Request, fn: Callable[[], Any]) -> Any:
        rid = request_id_of(request)
        try:
            enabled()
            return fn()
        except AppError as exc:
            exc = _with_request_id(exc, rid)
            headers = getattr(exc, "headers", None)
            if headers:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
                    headers=headers,
                )
            raise exc from None

    def get_tribunal_status(
        request: Request,
        portfolio_ids: list[str] = IdsQuery,
        portfolio_id: str | None = IdQuery,
        _auth: AuthContext = Auth,
    ) -> Any:
        ids = _query_ids(portfolio_ids, portfolio_id)
        return run(request, lambda: getter().status(_auth.user_id, ids))

    def get_tribunal_latest(
        request: Request,
        portfolio_ids: list[str] = IdsQuery,
        portfolio_id: str | None = IdQuery,
        _auth: AuthContext = Auth,
    ) -> Any:
        ids = _query_ids(portfolio_ids, portfolio_id)
        return run(request, lambda: getter().latest(_auth.user_id, ids))

    def start_tribunal_session(
        request: Request, payload: Any = Body(default=None), _auth: AuthContext = Auth,
    ) -> Any:
        def do() -> Any:
            body = _parse(TribunalStartRequest, payload)
            stream = getter().start(_auth.user_id, body.portfolio_ids, force_new=body.force_new)
            return StreamingResponse(
                stream,
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        return run(request, do)

    add("GET", "/doctor/tribunal/status", get_tribunal_status)
    add("POST", "/doctor/tribunal/sessions", start_tribunal_session)
    add("GET", "/doctor/tribunal/sessions/latest", get_tribunal_latest)
