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
