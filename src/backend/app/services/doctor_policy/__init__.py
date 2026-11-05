"""Portfolio Doctor 2.0: personal policy rules evaluated deterministically.

Contract: docs/doctor2/api-contracts.md; methodology:
docs/doctor2/financial-methodology.md.
"""

from .evaluator import (
    PolicyEvaluation,
    build_evaluation_response,
    evaluate_policy,
    evaluate_rule,
    summarize,
)
from .metrics import (
    METHODOLOGY_VERSION,
    METRIC_CODES,
    METRIC_REGISTRY,
    MetricDefinition,
    MetricValue,
    canonical_securities,
    compute_metrics,
    format_it,
    metric_definitions,
    policy_asset_class,
)
from .scope import (
    MAX_SCOPE_PORTFOLIOS,
    ScopeError,
    build_scope,
    normalize_scope_ids,
    scope_fingerprint,
    scope_type,
)
from .snapshot import DoctorSnapshot, build_snapshot, is_cash_holding, snapshot_from_holdings
from .templates import TEMPLATE_DISCLAIMER, TEMPLATE_VERSION, get_template, list_templates
from .validator import (
    EPSILON,
    MAX_RULES,
    PolicyValidationError,
    canonical_json,
    diff_documents,
    document_hash,
    normalize_policy_document,
    validate_and_normalize,
    validate_policy_document,
)

__all__ = [
    "DoctorSnapshot",
    "EPSILON",
    "MAX_RULES",
    "MAX_SCOPE_PORTFOLIOS",
    "METHODOLOGY_VERSION",
    "METRIC_CODES",
    "METRIC_REGISTRY",
    "MetricDefinition",
    "MetricValue",
    "PolicyEvaluation",
    "PolicyValidationError",
    "ScopeError",
    "TEMPLATE_DISCLAIMER",
    "TEMPLATE_VERSION",
    "build_evaluation_response",
    "build_scope",
    "build_snapshot",
    "canonical_json",
    "canonical_securities",
    "compute_metrics",
    "diff_documents",
    "document_hash",
    "evaluate_policy",
    "evaluate_rule",
    "format_it",
    "get_template",
    "is_cash_holding",
    "list_templates",
    "metric_definitions",
    "normalize_policy_document",
    "normalize_scope_ids",
    "policy_asset_class",
    "scope_fingerprint",
    "scope_type",
    "snapshot_from_holdings",
    "summarize",
    "validate_and_normalize",
    "validate_policy_document",
]
