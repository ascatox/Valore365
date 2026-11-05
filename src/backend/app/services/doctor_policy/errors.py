"""Errors of the Doctor 2.0 policy service (docs/doctor2/api-contracts.md §5).

All are :class:`app.errors.AppError` subclasses, so the app-wide handler
renders them as ``{"error": {"code", "message", "details"}}``. ``details``
always carries ``field_errors`` and ``retryable``; the REST layer adds
``request_id``. Copilot tools can catch :class:`DoctorPolicyError` and read
``code``/``message``.
"""

from __future__ import annotations

from typing import Any

from ...errors import AppError


def error_details(
    *, field_errors: list[dict[str, Any]] | None = None, retryable: bool = False, request_id: str | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {"field_errors": list(field_errors or []), "retryable": bool(retryable)}
    if request_id is not None:
        details["request_id"] = request_id
    return details


class DoctorPolicyError(AppError):
    code = "invalid_request"
    status_code = 400
    retryable = False

    def __init__(self, message: str, *, field_errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(
            code=type(self).code,
            message=message,
            status_code=type(self).status_code,
            details=error_details(field_errors=field_errors, retryable=type(self).retryable),
        )
        self.field_errors = list(field_errors or [])


class InvalidRequest(DoctorPolicyError):
    code = "invalid_request"
    status_code = 400


class PolicyValidationFailed(DoctorPolicyError):
    code = "validation_error"
    status_code = 422


class NotFound(DoctorPolicyError):
    code = "not_found"
    status_code = 404


class VersionConflict(DoctorPolicyError):
    code = "version_conflict"
    status_code = 409


class ConfirmationInvalid(DoctorPolicyError):
    code = "confirmation_invalid"
    status_code = 409


class FeatureDisabled(DoctorPolicyError):
    code = "feature_disabled"
    status_code = 404


class NotImplementedYet(DoctorPolicyError):
    code = "not_implemented"
    status_code = 501
