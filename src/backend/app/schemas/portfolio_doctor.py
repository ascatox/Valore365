from typing import Literal

from pydantic import BaseModel, Field


class PortfolioHealthSummary(BaseModel):
    risk_level: Literal["low", "medium", "high", "unknown"]
    diversification: Literal["excellent", "good", "moderate", "weak", "unknown"]
    overlap: Literal["low", "moderate", "high", "unknown"]
    cost_efficiency: Literal["low_cost", "moderate_cost", "high_cost", "unknown"]


class PortfolioHealthMetrics(BaseModel):
    geographic_exposure: dict[str, float] = Field(default_factory=dict)
    sector_exposure: dict[str, float] = Field(default_factory=dict)
    max_position_weight: float = Field(default=0, ge=0, le=100)
    overlap_score: float = Field(default=0, ge=0, le=100)
    portfolio_volatility: float | None = Field(default=None, ge=0)
    weighted_ter: float | None = Field(default=None, ge=0)


class PortfolioHealthCategoryScores(BaseModel):
    diversification: int = Field(default=0, ge=0, le=25)
    risk: int = Field(default=0, ge=0, le=25)
    concentration: int = Field(default=0, ge=0, le=20)
    overlap: int = Field(default=0, ge=0, le=15)
    cost_efficiency: int = Field(default=0, ge=0, le=15)


class PortfolioHealthAlert(BaseModel):
    severity: Literal["info", "warning", "critical"]
    type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, object] | None = None


class PortfolioHealthSuggestion(BaseModel):
    priority: Literal["low", "medium", "high"]
    message: str = Field(min_length=1)


class PortfolioHealthResponse(BaseModel):
    portfolio_id: int = Field(ge=1)
    score: int = Field(ge=0, le=100)
    summary: PortfolioHealthSummary
    metrics: PortfolioHealthMetrics
    category_scores: PortfolioHealthCategoryScores
    alerts: list[PortfolioHealthAlert] = Field(default_factory=list)
    suggestions: list[PortfolioHealthSuggestion] = Field(default_factory=list)


class MonteCarloYearProjection(BaseModel):
    year: int = Field(ge=0)
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class MonteCarloProjectionResponse(BaseModel):
    portfolio_id: int = Field(ge=1)
    num_simulations: int
    horizons: list[int]
    projections: list[MonteCarloYearProjection]
    annualized_mean_return_pct: float
    annualized_volatility_pct: float


class DecumulationYearProjection(BaseModel):
    year: int = Field(ge=1)
    age: int | None = Field(default=None, ge=18, le=120)
    target_net_spending: float = Field(ge=0)
    gross_withdrawal: float = Field(ge=0)
    estimated_taxes: float = Field(ge=0)
    net_withdrawal: float = Field(ge=0)
    other_income: float = Field(ge=0)
    net_spending_after_tax: float = Field(ge=0)
    p25_ending_capital: float = Field(ge=0)
    p50_ending_capital: float = Field(ge=0)
    p75_ending_capital: float = Field(ge=0)
    p50_effective_withdrawal_rate_pct: float = Field(ge=0)
    depletion_probability_pct: float = Field(ge=0, le=100)


class DecumulationPlanResponse(BaseModel):
    portfolio_id: int = Field(ge=1)
    initial_capital: float = Field(ge=0)
    annual_withdrawal: float = Field(ge=0)
    annual_other_income: float = Field(ge=0)
    inflation_rate_pct: float = Field(ge=0)
    capital_gains_tax_rate_pct: float = Field(ge=0, le=100)
    estimated_embedded_gain_ratio_pct: float = Field(ge=0, le=100)
    horizon_years: int = Field(ge=1)
    num_simulations: int = Field(ge=0)
    annualized_mean_return_pct: float
    annualized_volatility_pct: float
    sustainable_withdrawal: float = Field(ge=0)
    success_rate_pct: float = Field(ge=0, le=100)
    depletion_probability_pct: float = Field(ge=0, le=100)
    p25_terminal_value: float = Field(ge=0)
    p50_terminal_value: float = Field(ge=0)
    p75_terminal_value: float = Field(ge=0)
    depletion_year_p50: int | None = Field(default=None, ge=1)
    projections: list[DecumulationYearProjection] = Field(default_factory=list)


class AggregateDecumulationPlanResponse(BaseModel):
    portfolio_ids: list[int] = Field(default_factory=list, min_length=1)
    base_currency: str = Field(min_length=1)
    initial_capital: float = Field(ge=0)
    annual_withdrawal: float = Field(ge=0)
    annual_other_income: float = Field(ge=0)
    inflation_rate_pct: float = Field(ge=0)
    capital_gains_tax_rate_pct: float = Field(ge=0, le=100)
    estimated_embedded_gain_ratio_pct: float = Field(ge=0, le=100)
    horizon_years: int = Field(ge=1)
    num_simulations: int = Field(ge=0)
    annualized_mean_return_pct: float
    annualized_volatility_pct: float
    sustainable_withdrawal: float = Field(ge=0)
    success_rate_pct: float = Field(ge=0, le=100)
    depletion_probability_pct: float = Field(ge=0, le=100)
    p25_terminal_value: float = Field(ge=0)
    p50_terminal_value: float = Field(ge=0)
    p75_terminal_value: float = Field(ge=0)
    depletion_year_p50: int | None = Field(default=None, ge=1)
    projections: list[DecumulationYearProjection] = Field(default_factory=list)


class StressTestAssetImpact(BaseModel):
    symbol: str
    name: str
    weight_pct: float
    estimated_loss_pct: float


class StressTestScenarioResult(BaseModel):
    scenario_id: str = Field(min_length=1)
    scenario_name: str = Field(min_length=1)
    scenario_type: Literal["historical", "shock"]
    period: str | None = None
    estimated_portfolio_impact_pct: float
    max_drawdown_pct: float | None = None
    recovery_months: int | None = None
    benchmark_drawdown_pct: float | None = None
    risk_level: Literal["low", "medium", "high", "critical"]
    most_impacted_assets: list[StressTestAssetImpact] = Field(default_factory=list)


class StressTestResponse(BaseModel):
    portfolio_id: int = Field(ge=1)
    scenarios: list[StressTestScenarioResult] = Field(default_factory=list)
    portfolio_volatility_pct: float | None = None
    analysis_date: str


class XRayHolding(BaseModel):
    symbol: str
    name: str
    aggregated_weight_pct: float
    etf_contributors: list[str] = Field(default_factory=list)


class XRayEtfDetail(BaseModel):
    asset_id: int | None = Field(default=None, ge=1)
    symbol: str
    name: str
    portfolio_weight_pct: float
    holdings_available: bool
    holdings_source: Literal["justetf", "yfinance", "missing"] = "missing"
    failure_reason: str | None = None
    top_holdings: list[XRayHolding] = Field(default_factory=list)


class XRayCoverageIssue(BaseModel):
    asset_id: int = Field(ge=1)
    symbol: str
    name: str
    reason: str


class XRayResponse(BaseModel):
    portfolio_id: int = Field(ge=1)
    aggregated_holdings: list[XRayHolding] = Field(default_factory=list)
    etf_details: list[XRayEtfDetail] = Field(default_factory=list)
    etf_count: int = Field(ge=0)
    coverage_pct: float = Field(ge=0, le=100)
    aggregated_country_exposure: dict[str, float] = Field(default_factory=dict)
    aggregated_sector_exposure: dict[str, float] = Field(default_factory=dict)
    coverage_issues: list[XRayCoverageIssue] = Field(default_factory=list)
