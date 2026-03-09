from typing import Literal

from pydantic import BaseModel, Field
from .portfolio_doctor import PortfolioHealthCategoryScores


class ParsedPositionInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)
    value: float = Field(gt=0)


class InstantAnalyzeRequest(BaseModel):
    input_mode: Literal["text", "raw_text"] = "raw_text"
    positions: list[ParsedPositionInput] = Field(default_factory=list)
    raw_text: str | None = None


class InstantAnalyzeLineError(BaseModel):
    line: int = Field(ge=1)
    raw: str
    error: str


class InstantAnalyzeUnresolvedItem(BaseModel):
    identifier: str
    raw: str | None = None
    line: int | None = Field(default=None, ge=1)
    error: str


class PortfolioAnalyzeSummary(BaseModel):
    total_value: float = Field(ge=0)
    score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high", "unknown"]
    diversification: Literal["excellent", "good", "moderate", "weak", "unknown"]
    overlap: Literal["low", "moderate", "high", "unknown"]
    cost_efficiency: Literal["low_cost", "moderate_cost", "high_cost", "unknown"]


class PortfolioAnalyzeMetrics(BaseModel):
    geographic_exposure: dict[str, float] = Field(default_factory=dict)
    max_position_weight: float = Field(default=0, ge=0, le=100)
    overlap_score: float = Field(default=0, ge=0, le=100)
    portfolio_volatility: float | None = Field(default=None, ge=0)
    weighted_ter: float | None = Field(default=None, ge=0)


class ResolvedPosition(BaseModel):
    identifier: str
    resolved_symbol: str
    resolved_name: str
    value: float = Field(gt=0)
    weight: float = Field(ge=0, le=100)
    status: Literal["resolved"] = "resolved"


class PortfolioAnalyzeAlert(BaseModel):
    severity: Literal["info", "warning", "critical"]
    code: str
    message: str


class PortfolioAnalyzeSuggestion(BaseModel):
    code: str
    message: str


class InstantAnalyzeCta(BaseModel):
    show_signup: bool = True
    message: str


class InstantAnalyzeResponse(BaseModel):
    summary: PortfolioAnalyzeSummary
    positions: list[ResolvedPosition] = Field(default_factory=list)
    unresolved: list[InstantAnalyzeUnresolvedItem] = Field(default_factory=list)
    parse_errors: list[InstantAnalyzeLineError] = Field(default_factory=list)
    metrics: PortfolioAnalyzeMetrics
    category_scores: PortfolioHealthCategoryScores
    alerts: list[PortfolioAnalyzeAlert] = Field(default_factory=list)
    suggestions: list[PortfolioAnalyzeSuggestion] = Field(default_factory=list)
    cta: InstantAnalyzeCta
