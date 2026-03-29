from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from .portfolio_doctor import PortfolioHealthCategoryScores


class ParsedPositionInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9._-]+$")
    value: float = Field(gt=0, le=1_000_000_000_000)

    @field_validator("identifier", mode="before")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return value.strip()


class InstantAnalyzeRequest(BaseModel):
    input_mode: Literal["text", "raw_text"] = "raw_text"
    positions: list[ParsedPositionInput] = Field(default_factory=list, max_length=500)
    raw_text: str | None = Field(default=None, max_length=50000)


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
    asset_allocation: dict[str, float] = Field(default_factory=dict)
    max_position_weight: float = Field(default=0, ge=0, le=100)
    overlap_score: float = Field(default=0, ge=0, le=100)
    portfolio_volatility: float | None = Field(default=None, ge=0)
    weighted_ter: float | None = Field(default=None, ge=0)
    risk_score: float = Field(default=0, ge=0)
    estimated_drawdown: float = Field(default=0, ge=0, le=100)


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


class PortfolioTopInsight(BaseModel):
    id: str = Field(min_length=1)
    type: Literal["geo_concentration", "holding_overlap", "portfolio_risk"]
    severity: Literal["medium", "high"]
    score: int = Field(ge=1)
    title: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    explanation_data: dict[str, Any] = Field(default_factory=dict)
    cta_label: str = Field(default="Spiegamelo meglio")


class InstantAnalyzeResponse(BaseModel):
    summary: PortfolioAnalyzeSummary
    positions: list[ResolvedPosition] = Field(default_factory=list)
    unresolved: list[InstantAnalyzeUnresolvedItem] = Field(default_factory=list)
    parse_errors: list[InstantAnalyzeLineError] = Field(default_factory=list)
    metrics: PortfolioAnalyzeMetrics
    category_scores: PortfolioHealthCategoryScores
    alerts: list[PortfolioAnalyzeAlert] = Field(default_factory=list)
    suggestions: list[PortfolioAnalyzeSuggestion] = Field(default_factory=list)
    insights: list[PortfolioTopInsight] = Field(default_factory=list, max_length=3)
    cta: InstantAnalyzeCta


class InstantInsightExplainRequest(BaseModel):
    insight: PortfolioTopInsight


class InstantInsightExplainResponse(BaseModel):
    insight_id: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    source: Literal["ai", "template"]
