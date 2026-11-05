"""Scenario Lab schemas (docs/doctor2/api-contracts.md §8).

Inputs are strict: amounts are finite JSON numbers (no strings, booleans,
NaN or infinity), at most 50 operations / target weights, weights 0-100
summing to at most 100. Extra fields are rejected.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .doctor_policy import INT4_MAX, DataQuality, EvaluationSummary, MetricValueRead, PolicyScope, RuleResult

MAX_OPERATIONS = 50
MAX_TARGET_WEIGHTS = 50
MAX_AMOUNT = 1e12
WEIGHT_SUM_TOLERANCE = 1e-6
SCENARIO_DISCLAIMER = "Simulazione teorica; nessun ordine eseguito."

ScenarioMode = Literal["manual", "new_cash_only", "rebalance"]

Amount = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=MAX_AMOUNT)]
PositiveAmount = Annotated[float, Field(strict=True, allow_inf_nan=False, gt=0, le=MAX_AMOUNT)]
Pct = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=100)]
# target_weights key: asset_id as a string, or a symbol (bounded length).
TargetKey = Annotated[str, Field(min_length=1, max_length=40)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# input
# ---------------------------------------------------------------------------


class ScenarioOperation(_Strict):
    """One buy/sell of an asset already in the scope (manual mode)."""

    asset_id: Annotated[int, Field(strict=True, gt=0)] | None = None
    symbol: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    action: Literal["buy", "sell"]
    amount: PositiveAmount

    @model_validator(mode="after")
    def _needs_asset(self) -> ScenarioOperation:
        if self.asset_id is None and not (self.symbol or "").strip():
            raise ValueError("Indica symbol o asset_id")
        return self


class ScenarioConstraints(_Strict):
    no_sell: Annotated[bool, Field(strict=True)] = False
    max_turnover_pct: Pct | None = None
    keep_equity_total: Annotated[bool, Field(strict=True)] = False
    # MVP extension: also spend the current cash balance (default: only new_cash + sales).
    use_cash_balance: Annotated[bool, Field(strict=True)] = False


class FeeModel(_Strict):
    """Cost per operation: ``pct`` % of the traded amount + ``fixed`` (base currency)."""

    pct: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=10)] = 0.0
    fixed: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=10_000)] = 0.0


class ScenarioInput(_Strict):
    """One scenario, without the scope (an item of a compare request)."""

    mode: ScenarioMode
    new_cash: Amount = 0.0
    operations: list[ScenarioOperation] = Field(default_factory=list, max_length=MAX_OPERATIONS)
    # asset_id (as string, JSON object key) -> pct. rebalance: overall target
    # weights; new_cash_only: maximum weight per position.
    target_weights: dict[TargetKey, Pct] = Field(default_factory=dict)
    constraints: ScenarioConstraints = Field(default_factory=ScenarioConstraints)
    fee_model: FeeModel = Field(default_factory=FeeModel)
    tax_model: Literal["none"] = "none"
    label: Annotated[str, Field(max_length=80)] | None = None

    @field_validator("target_weights")
    @classmethod
    def _weights(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > MAX_TARGET_WEIGHTS:
            raise ValueError(f"Al massimo {MAX_TARGET_WEIGHTS} pesi obiettivo")
        if sum(value.values()) > 100.0 + WEIGHT_SUM_TOLERANCE:
            raise ValueError("La somma dei pesi obiettivo supera 100")
        return value


class ScenarioRequest(ScenarioInput):
    portfolio_ids: list[Annotated[int, Field(strict=True)]] = Field(min_length=1, max_length=20)
    snapshot_id: Annotated[str, Field(max_length=64)] | None = None
    policy_version: Annotated[int, Field(strict=True, ge=0, le=INT4_MAX)] | None = None


class ScenarioCompareRequest(_Strict):
    portfolio_ids: list[Annotated[int, Field(strict=True)]] = Field(min_length=1, max_length=20)
    snapshot_id: Annotated[str, Field(max_length=64)] | None = None
    policy_version: Annotated[int, Field(strict=True, ge=0, le=INT4_MAX)] | None = None
    scenarios: list[ScenarioInput] = Field(min_length=2, max_length=3)


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------


class VolatilityEstimate(BaseModel):
    value: float | None = None
    status: Literal["not_available"] = "not_available"
    reason: str


class ScenarioSide(BaseModel):
    """Portfolio state before or after a scenario (metrics over the invested value)."""

    invested_value: float
    cash_value: float
    total_value: float
    metrics: dict[str, MetricValueRead]
    evaluation_status: Literal["ready", "no_policy", "empty_portfolio"]
    evaluation_summary: EvaluationSummary
    rule_results: list[RuleResult] = Field(default_factory=list)
    volatility: VolatilityEstimate


class ScenarioChange(BaseModel):
    asset_id: int
    symbol: str
    name: str | None = None
    isin: str | None = None
    asset_class: str
    action: Literal["buy", "sell", "hold"]
    before_value: float
    after_value: float
    delta_value: float
    before_weight: float
    after_weight: float
    delta_weight: float
    fees: float = 0.0


class RuleChange(BaseModel):
    rule_id: str
    metric_code: str
    label: str
    reason: str  # reason of the state after the scenario
    before_status: str
    after_status: str
    before_actual: float | None = None
    after_actual: float | None = None


class ScenarioCosts(BaseModel):
    total: float = 0.0
    variable: float = 0.0
    fixed: float = 0.0
    operations: int = 0
    fee_model: FeeModel = Field(default_factory=FeeModel)


class ScenarioResult(BaseModel):
    label: str | None = None
    mode: ScenarioMode
    feasible: bool
    infeasible_code: str | None = None
    infeasible_reason: str | None = None
    scope: PolicyScope
    policy_id: int | None = None
    policy_version: int | None = None
    before: ScenarioSide
    after: ScenarioSide | None = None
    changes: list[ScenarioChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    violations_resolved: list[RuleChange] = Field(default_factory=list)
    violations_new: list[RuleChange] = Field(default_factory=list)
    required_new_cash: float | None = None
    total_before: float
    total_after: float | None = None
    cash_in: float
    costs: ScenarioCosts
    turnover_pct: float | None = None
    methodology_version: str
    snapshot_id: str
    data_quality: DataQuality
    calculated_at: str
    tax_model: Literal["none"] = "none"
    disclaimer: str = SCENARIO_DISCLAIMER


class ScenarioRankItem(BaseModel):
    index: int
    label: str | None = None
    rank: int
    feasible: bool
    failed_after: int | None = None
    unknown_after: int | None = None
    violations_resolved: int = 0
    violations_new: int = 0
    costs: float = 0.0
    cash_in: float = 0.0
    turnover_pct: float | None = None


class ScenarioComparison(BaseModel):
    scope: PolicyScope
    policy_id: int | None = None
    policy_version: int | None = None
    snapshot_id: str
    methodology_version: str
    calculated_at: str
    data_quality: DataQuality
    current: ScenarioSide  # state without any scenario (the ``before`` of each one)
    scenarios: list[ScenarioResult]
    ranking: list[ScenarioRankItem]
    best_index: int | None = None
    explanation: str
    disclaimer: str = SCENARIO_DISCLAIMER
