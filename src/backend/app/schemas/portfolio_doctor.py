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
    # Peso maggiore tra gli strumenti che non sono fondi/ETF (titoli singoli,
    # obbligazioni singole...). None = non calcolato: vale max_position_weight.
    max_single_security_weight: float | None = Field(default=None, ge=0, le=100)
    overlap_score: float = Field(default=0, ge=0, le=100)
    portfolio_volatility: float | None = Field(default=None, ge=0)
    weighted_ter: float | None = Field(default=None, ge=0)

    @property
    def concentration_weight(self) -> float:
        """Peso usato per alert, suggerimenti e punteggi di concentrazione."""
        if self.max_single_security_weight is not None:
            return self.max_single_security_weight
        return self.max_position_weight


class PortfolioHealthCategoryScores(BaseModel):
    diversification: int = Field(default=0, ge=0, le=25)
    risk: int = Field(default=0, ge=0, le=25)
    concentration: int = Field(default=0, ge=0, le=20)
    overlap: int = Field(default=0, ge=0, le=15)
    cost_efficiency: int = Field(default=0, ge=0, le=15)


class VolatilityInfo(BaseModel):
    """A volatility figure with its declared methodology (TASK-40).

    There is no canonical volatility: stress test and health score use two
    different measures, each named and described here.
    """
    name: str
    value_pct: float | None = None
    method: str
    period: str
    is_floored: bool = False
    # Floor applied (stress only): long-term volatility of the class mix.
    floor_pct: float | None = None
    # Value before the floor (stress only).
    unfloored_pct: float | None = None


class PortfolioHealthScoreDeduction(BaseModel):
    """One rule that removed points from a category score."""
    category: Literal["diversification", "risk", "concentration", "overlap", "cost_efficiency"]
    code: str = Field(min_length=1)
    points: int = Field(gt=0)
    reason: str = Field(min_length=1)


class PortfolioHealthEducation(BaseModel):
    code: str = Field(min_length=1)
    title: str = Field(min_length=1)
    what_it_means: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    how_to_read_it: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    copilot_prompts: list[str] = Field(default_factory=list)


class PortfolioHealthAlert(BaseModel):
    severity: Literal["info", "warning", "critical"]
    type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, object] | None = None
    education: PortfolioHealthEducation | None = None


class PortfolioHealthSuggestion(BaseModel):
    priority: Literal["low", "medium", "high"]
    message: str = Field(min_length=1)


class PortfolioHealthResponse(BaseModel):
    # 0 per la vista aggregata (gli id selezionati sono in portfolio_ids).
    portfolio_id: int = Field(ge=0)
    portfolio_ids: list[int] | None = None
    score: int = Field(ge=0, le=100)
    summary: PortfolioHealthSummary
    metrics: PortfolioHealthMetrics
    category_scores: PortfolioHealthCategoryScores
    # Rules that removed points (sum per category = category max - score).
    score_deductions: list[PortfolioHealthScoreDeduction] = Field(default_factory=list)
    # Methodology of metrics.portfolio_volatility.
    volatility: VolatilityInfo | None = None
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
    # 0 per la vista aggregata (gli id selezionati sono in portfolio_ids).
    portfolio_id: int = Field(ge=0)
    portfolio_ids: list[int] | None = None
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
    capital_floor: float = Field(default=0, ge=0)
    floor_breach_probability_pct: float = Field(default=0, ge=0, le=100)


class DecumulationPlanResponse(BaseModel):
    portfolio_id: int = Field(ge=1)
    initial_capital: float = Field(ge=0)
    annual_withdrawal: float = Field(ge=0)
    annual_other_income: float = Field(ge=0)
    inflation_rate_pct: float = Field(ge=0)
    capital_gains_tax_rate_pct: float = Field(ge=0, le=100)
    estimated_embedded_gain_ratio_pct: float = Field(ge=0, le=100)
    horizon_years: int = Field(ge=1)
    capital_floor: float = Field(default=0, ge=0)
    pension_annual: float = Field(default=0, ge=0)
    pension_start_year: int | None = Field(default=None, ge=1)
    num_simulations: int = Field(ge=0)
    annualized_mean_return_pct: float
    annualized_volatility_pct: float
    sustainable_withdrawal: float = Field(ge=0)
    success_rate_pct: float = Field(ge=0, le=100)
    depletion_probability_pct: float = Field(ge=0, le=100)
    floor_breach_probability_pct: float = Field(default=0, ge=0, le=100)
    p25_terminal_value: float = Field(ge=0)
    p50_terminal_value: float = Field(ge=0)
    p75_terminal_value: float = Field(ge=0)
    depletion_year_p50: int | None = Field(default=None, ge=1)
    floor_breach_year_p50: int | None = Field(default=None, ge=1)
    p50_terminal_value_real: float = Field(default=0, ge=0)
    terminal_target_min: float = Field(default=0, ge=0)
    terminal_target_max: float = Field(default=0, ge=0)
    terminal_below_range_probability_pct: float | None = Field(default=None, ge=0, le=100)
    terminal_in_range_probability_pct: float | None = Field(default=None, ge=0, le=100)
    terminal_above_range_probability_pct: float | None = Field(default=None, ge=0, le=100)
    withdrawal_for_terminal_max: float | None = Field(default=None, ge=0)
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
    capital_floor: float = Field(default=0, ge=0)
    pension_annual: float = Field(default=0, ge=0)
    pension_start_year: int | None = Field(default=None, ge=1)
    num_simulations: int = Field(ge=0)
    annualized_mean_return_pct: float
    annualized_volatility_pct: float
    sustainable_withdrawal: float = Field(ge=0)
    success_rate_pct: float = Field(ge=0, le=100)
    depletion_probability_pct: float = Field(ge=0, le=100)
    floor_breach_probability_pct: float = Field(default=0, ge=0, le=100)
    p25_terminal_value: float = Field(ge=0)
    p50_terminal_value: float = Field(ge=0)
    p75_terminal_value: float = Field(ge=0)
    depletion_year_p50: int | None = Field(default=None, ge=1)
    floor_breach_year_p50: int | None = Field(default=None, ge=1)
    p50_terminal_value_real: float = Field(default=0, ge=0)
    terminal_target_min: float = Field(default=0, ge=0)
    terminal_target_max: float = Field(default=0, ge=0)
    terminal_below_range_probability_pct: float | None = Field(default=None, ge=0, le=100)
    terminal_in_range_probability_pct: float | None = Field(default=None, ge=0, le=100)
    terminal_above_range_probability_pct: float | None = Field(default=None, ge=0, le=100)
    withdrawal_for_terminal_max: float | None = Field(default=None, ge=0)
    projections: list[DecumulationYearProjection] = Field(default_factory=list)


class StressTestAssetImpact(BaseModel):
    symbol: str
    name: str
    weight_pct: float
    estimated_loss_pct: float
    # Shared asset class (shock scenarios only).
    asset_class: str | None = None


class StressTestClassImpact(BaseModel):
    """Per-class view of a scenario.

    Shock scenarios fill ``shock_pct``; historical scenarios fill
    ``drawdown_pct`` (return of the class over the window) and ``source``
    (one row per class and source: real prices or class proxy).
    """
    asset_class: str
    weight_pct: float
    # Base shock of the class in the scenario (tech multiplier excluded).
    shock_pct: float | None = None
    # Historical scenarios: drawdown used for the class (real or proxy).
    drawdown_pct: float | None = None
    source: Literal["historical", "proxy"] | None = None
    # weight x applied shock/drawdown, in portfolio percentage points.
    contribution_pct: float


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
    # Historical scenarios only: "historical" when real prices cover at least
    # 60% of the weight, "proxy" (class drawdown proxies) below it,
    # "not_available" for an empty portfolio. coverage_pct = weight with real
    # prices in the window (cash included).
    method: Literal["historical", "proxy", "not_available"] | None = None
    coverage_pct: float | None = None
    # Historical scenarios: Italian note for the user, set whenever any part
    # of the estimate uses the USD class proxies (FX effect not modelled).
    methodology_note: str | None = None
    # Classes with a non-zero shock (shock scenarios), per-class breakdown
    # and flags such as "unknown_asset_class_equity_shock".
    affected_classes: list[str] = Field(default_factory=list)
    class_breakdown: list[StressTestClassImpact] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class StressTestResponse(BaseModel):
    # 0 per la vista aggregata (gli id selezionati sono in portfolio_ids).
    portfolio_id: int = Field(ge=0)
    portfolio_ids: list[int] | None = None
    scenarios: list[StressTestScenarioResult] = Field(default_factory=list)
    portfolio_volatility_pct: float | None = None
    volatility: VolatilityInfo | None = None
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
    investment_focus: str | None = None
    portfolio_weight_pct: float
    holdings_available: bool
    holdings_source: Literal["justetf", "yfinance", "missing"] = "missing"
    failure_reason: str | None = None
    top_holdings: list[XRayHolding] = Field(default_factory=list)
    # TASK-48: what kind of look-through this position gets and how deep it goes.
    # fund: a fund with listed top holdings; direct_stock: a single share (its own
    # underlying); no_lookthrough: gold/commodity/crypto; missing: no data.
    lookthrough_kind: Literal["fund", "direct_stock", "no_lookthrough", "missing"] = "missing"
    # TASK-52: available (holdings known / single share), not_applicable (gold,
    # commodity, bond, money market, crypto: no equity basket to decompose),
    # missing (equity or unclassified fund without holdings data). Reason in Italian.
    lookthrough_status: Literal["available", "not_applicable", "missing"] = "missing"
    lookthrough_reason: str | None = None
    # Sum of the listed top-holding weights, in % of the fund (None without holdings).
    listed_holdings_pct: float | None = None
    # Provider of the data used for this position and its reference date (ISO).
    data_source: Literal["justetf", "yahoo", "none"] = "none"
    data_as_of: str | None = None
    # holdings_date: as-of date stated by the provider; fetched_at: when the
    # justETF profile was stored; fetch_time: when Yahoo was asked (process cache).
    data_as_of_basis: Literal["holdings_date", "fetched_at", "fetch_time"] | None = None


class XRayCoverageIssue(BaseModel):
    asset_id: int = Field(ge=1)
    symbol: str
    name: str
    reason: str
    # TASK-52: a not_applicable position is listed here too (no holdings), but it is not missing data.
    lookthrough_status: Literal["available", "not_applicable", "missing"] = "missing"
    lookthrough_reason: str | None = None


class XRayResponse(BaseModel):
    # 0 per la vista aggregata (gli id selezionati sono in portfolio_ids).
    portfolio_id: int = Field(ge=0)
    portfolio_ids: list[int] | None = None
    aggregated_holdings: list[XRayHolding] = Field(default_factory=list)
    etf_details: list[XRayEtfDetail] = Field(default_factory=list)
    etf_count: int = Field(ge=0)
    # Legacy: weight of the positions with at least one top holding over all
    # positions. Same meaning as funds_with_holdings_pct (TASK-48), kept as is.
    coverage_pct: float = Field(ge=0, le=100)
    # TASK-48 — every percentage below is over coverage_denominator (market value
    # of the positions, cash excluded).
    lookthrough_coverage_pct: float = Field(default=0.0, ge=0, le=100)
    funds_with_holdings_pct: float = Field(default=0.0, ge=0, le=100)
    classified_country_pct: float = Field(default=0.0, ge=0, le=100)
    classified_sector_pct: float = Field(default=0.0, ge=0, le=100)
    unclassified_country_pct: float = Field(default=0.0, ge=0, le=100)
    unclassified_sector_pct: float = Field(default=0.0, ge=0, le=100)
    # TASK-52 — decomposed value of the applicable positions / their value
    # (applicable_denominator); None when no position is applicable.
    applicable_lookthrough_coverage_pct: float | None = Field(default=None, ge=0, le=100)
    # Shares of coverage_denominator by lookthrough_status (they sum to 100).
    available_pct: float = Field(default=0.0, ge=0, le=100)
    not_applicable_pct: float = Field(default=0.0, ge=0, le=100)
    missing_pct: float = Field(default=0.0, ge=0, le=100)
    applicable_denominator: str = ""
    coverage_denominator: str = ""
    coverage_note: str = ""
    # Oldest reference date (ISO) of the provider data used; None without data.
    data_as_of: str | None = None
    aggregated_country_exposure: dict[str, float] = Field(default_factory=dict)
    aggregated_sector_exposure: dict[str, float] = Field(default_factory=dict)
    coverage_issues: list[XRayCoverageIssue] = Field(default_factory=list)
    # TASK-87: true when the scope has no positions (every field above is then
    # empty or zero and coverage_note says so); not an error.
    is_empty: bool = False
