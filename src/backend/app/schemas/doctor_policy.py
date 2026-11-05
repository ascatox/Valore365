"""Pydantic schemas of Portfolio Doctor 2.0 personal policies.

Binding contract: docs/doctor2/api-contracts.md (sections 2-5).

Request bodies carry the policy ``document`` as a raw ``dict``: the strict
validation is done by ``app.services.doctor_policy.validator`` so that every
error comes back as a ``FieldError`` with a path such as
``rules[0].max_value`` (a Pydantic error would be a FastAPI 422 in another
shape). ``PolicyDocument`` / ``PolicyRule`` describe the *normalized* document
(what the validator returns and what is stored).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PolicyOperator = Literal["min", "max", "range"]
PolicySeverity = Literal["low", "medium", "high"]
PolicyUnit = Literal["pct"]
RuleStatus = Literal["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE", "INACTIVE"]
MetricQuality = Literal["ok", "partial", "stale", "missing"]
DataQualityStatus = Literal["ok", "stale", "partial", "unknown"]
EvaluationStatus = Literal["ready", "no_policy", "empty_portfolio"]
ScopeType = Literal["single", "aggregate"]
PolicySource = Literal["manual", "copilot", "template", "restore"]
DiffChange = Literal["added", "removed", "modified"]


# ---------------------------------------------------------------------------
# Policy document (contract §3)
# ---------------------------------------------------------------------------


class PolicyRule(BaseModel):
    """One rule of a normalized policy document."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    metric_code: str
    operator: PolicyOperator
    min_value: float | None = None
    max_value: float | None = None
    unit: PolicyUnit = "pct"
    precision: int = Field(default=1, ge=0, le=3)
    severity: PolicySeverity = "medium"
    warning_margin: float = Field(default=2.0, ge=0, le=100)
    min_coverage_pct: float = Field(default=80.0, ge=0, le=100)
    max_data_age_days: int = Field(default=5, ge=1, le=365)
    enabled: bool = True
    label: str | None = Field(default=None, max_length=80)


class PolicyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    rules: list[PolicyRule] = Field(default_factory=list, max_length=20)


class FieldError(BaseModel):
    field: str
    code: str
    message: str


# ---------------------------------------------------------------------------
# Metric registry and evaluation (contract §2, §4)
# ---------------------------------------------------------------------------


class MetricDefinitionRead(BaseModel):
    code: str
    label: str
    unit: PolicyUnit = "pct"
    operators: list[PolicyOperator]
    denominator: str
    description: str
    source: str
    default_warning_margin: float
    methodology_version: str


class MetricContributor(BaseModel):
    symbol: str | None = None
    name: str | None = None
    isin: str | None = None
    weight_pct: float


class MetricEvidence(BaseModel):
    source: str
    denominator: str
    denominator_value: float | None = None
    contributors: list[MetricContributor] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    quote_as_of: str | None = None
    calculated_at: str
    methodology_version: str


class MetricValueRead(BaseModel):
    """Serialized ``MetricValue`` (used by Copilot / Scenario Lab)."""

    code: str
    value: float | None = None
    lower: float | None = None
    upper: float | None = None
    unit: PolicyUnit = "pct"
    coverage_pct: float | None = None
    quality: MetricQuality
    source: str
    denominator: str
    denominator_value: float | None = None
    contributors: list[MetricContributor] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RuleResult(BaseModel):
    rule_id: str
    metric_code: str
    label: str
    operator: PolicyOperator
    min_value: float | None = None
    max_value: float | None = None
    unit: PolicyUnit = "pct"
    precision: int = 1
    severity: PolicySeverity
    status: RuleStatus
    near_limit: bool = False
    actual: float | None = None
    actual_lower: float | None = None
    actual_upper: float | None = None
    breach_amount: float | None = None
    reason: str
    coverage_pct: float | None = None
    quality: MetricQuality
    evidence: MetricEvidence


class EvaluationSummary(BaseModel):
    passed: int = 0
    failed: int = 0
    unknown: int = 0
    not_applicable: int = 0
    inactive: int = 0
    near_limit: int = 0
    total: int = 0


class DataQuality(BaseModel):
    status: DataQualityStatus
    last_successful_price_sync: str | None = None
    last_sync_status: str | None = None
    stale_symbols: list[str] = Field(default_factory=list)
    missing_price_symbols: list[str] = Field(default_factory=list)
    oldest_price_at: str | None = None
    note: str | None = None


class PolicyScope(BaseModel):
    portfolio_ids: list[int]
    scope_type: ScopeType
    fingerprint: str


class PolicyEvaluationResponse(BaseModel):
    status: EvaluationStatus
    scope: PolicyScope
    policy_id: int | None = None
    policy_version: int | None = None
    policy_name: str | None = None
    snapshot_id: str
    snapshot_as_of: str | None = None
    calculated_at: str
    methodology_version: str
    data_quality: DataQuality
    summary: EvaluationSummary
    results: list[RuleResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Persistence / REST (contract §5)
# ---------------------------------------------------------------------------


class PolicyRead(BaseModel):
    id: int
    name: str
    scope: PolicyScope
    active: bool = True
    current_version: int
    document: PolicyDocument
    updated_at: str
    created_at: str


class PolicyReadEnvelope(BaseModel):
    policy: PolicyRead | None = None


class PolicyDiffItem(BaseModel):
    rule_id: str
    metric_code: str
    change: DiffChange
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class PolicyVersionRead(BaseModel):
    version_number: int
    schema_version: int = 1
    document: PolicyDocument
    document_hash: str
    source: PolicySource
    diff: list[PolicyDiffItem] = Field(default_factory=list)
    confirmed_at: str
    actor: str | None = None


class PolicyVersionsResponse(BaseModel):
    policy_id: int
    current_version: int
    versions: list[PolicyVersionRead] = Field(default_factory=list)


# Versions are stored in int4 columns: out-of-range values are a 400 field
# error, never a database error (500).
INT4_MAX = 2_147_483_647


class ValidateRequest(BaseModel):
    portfolio_ids: list[int] = Field(min_length=1, max_length=20)
    document: dict[str, Any]


class ValidateResponse(BaseModel):
    valid: bool
    field_errors: list[FieldError] = Field(default_factory=list)
    normalized_document: PolicyDocument | None = None


class PreviewRequest(BaseModel):
    portfolio_ids: list[int] = Field(min_length=1, max_length=20)
    document: dict[str, Any]
    base_version: int | None = Field(default=None, ge=0, le=INT4_MAX)
    source: Literal["manual", "copilot", "template"] = "manual"


class PolicyPreviewResponse(BaseModel):
    valid: bool
    field_errors: list[FieldError] = Field(default_factory=list)
    normalized_document: PolicyDocument | None = None
    diff: list[PolicyDiffItem] = Field(default_factory=list)
    evaluation_before: PolicyEvaluationResponse | None = None
    evaluation_after: PolicyEvaluationResponse | None = None
    confirmation_token: str | None = None
    expires_at: str | None = None
    base_version: int | None = None
    document_hash: str | None = None


class SaveRequest(BaseModel):
    portfolio_ids: list[int] = Field(min_length=1, max_length=20)
    # None keeps the current name of an existing policy (a save never renames
    # it implicitly); on create the default name "La mia policy" is used.
    name: str | None = Field(default=None, min_length=1, max_length=80)
    document: dict[str, Any]
    base_version: int | None = Field(default=None, ge=0, le=INT4_MAX)
    confirmation_token: str = Field(min_length=1)


class RestoreRequest(BaseModel):
    version_number: int = Field(ge=1, le=INT4_MAX)
    base_version: int | None = Field(default=None, ge=0, le=INT4_MAX)


class TemplateRead(BaseModel):
    template_id: str
    name: str
    description: str
    template_version: str
    illustrative: bool = True
    disclaimer: str
    document: PolicyDocument


class TemplatesResponse(BaseModel):
    template_version: str
    templates: list[TemplateRead] = Field(default_factory=list)


class MetricsResponse(BaseModel):
    methodology_version: str
    metrics: list[MetricDefinitionRead] = Field(default_factory=list)


class DoctorFeaturesRead(BaseModel):
    policy_enabled: bool
    simulator_enabled: bool
