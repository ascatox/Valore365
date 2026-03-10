from typing import Literal

from pydantic import BaseModel, Field


class PortfolioHealthSummary(BaseModel):
    risk_level: Literal["low", "medium", "high", "unknown"]
    diversification: Literal["excellent", "good", "moderate", "weak", "unknown"]
    overlap: Literal["low", "moderate", "high", "unknown"]
    cost_efficiency: Literal["low_cost", "moderate_cost", "high_cost", "unknown"]


class PortfolioHealthMetrics(BaseModel):
    geographic_exposure: dict[str, float] = Field(default_factory=dict)
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
    gross_withdrawal: float = Field(ge=0)
    net_withdrawal: float = Field(ge=0)
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
