from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ApiError


class UserSettingsRead(BaseModel):
    user_id: str
    broker_default_fee: float = Field(default=0, ge=0)


class UserSettingsUpdate(BaseModel):
    broker_default_fee: float = Field(ge=0)


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_currency: str = Field(min_length=3, max_length=3, pattern='^[A-Z]{3}$')
    timezone: str = Field(min_length=1, max_length=128)
    target_notional: float | None = Field(default=None, ge=0)
    cash_balance: float = Field(default=0.0, ge=0)


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    base_currency: str | None = Field(default=None, min_length=3, max_length=3, pattern='^[A-Z]{3}$')
    timezone: str | None = Field(default=None, min_length=1, max_length=128)
    target_notional: float | None = Field(default=None, ge=0)
    cash_balance: float | None = Field(default=None, ge=0)


class PortfolioRead(PortfolioCreate):
    id: int
    created_at: datetime


class PortfolioCloneRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class PortfolioCloneResponse(BaseModel):
    portfolio: PortfolioRead
    target_allocations_copied: int = Field(ge=0)


class TransactionCreate(BaseModel):
    portfolio_id: int = Field(ge=1)
    asset_id: int = Field(ge=1)
    side: Literal['buy', 'sell']
    trade_at: datetime
    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    fees: float = Field(default=0, ge=0)
    taxes: float = Field(default=0, ge=0)
    trade_currency: str = Field(min_length=3, max_length=3, pattern='^[A-Z]{3}$')
    notes: str | None = None


class TransactionRead(TransactionCreate):
    id: int


class TransactionUpdate(BaseModel):
    trade_at: datetime | None = None
    quantity: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, ge=0)
    fees: float | None = Field(default=None, ge=0)
    taxes: float | None = Field(default=None, ge=0)
    notes: str | None = None


class TransactionListItem(TransactionRead):
    symbol: str
    asset_name: str | None = None


class AssetLatestQuoteResponse(BaseModel):
    asset_id: int
    symbol: str
    provider: str
    provider_symbol: str
    price: float
    ts: datetime


class AssetCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=255)
    asset_type: Literal['stock', 'etf', 'crypto', 'bond', 'cash', 'fund']
    exchange_code: str | None = Field(default=None, max_length=16)
    exchange_name: str | None = Field(default=None, max_length=255)
    quote_currency: str = Field(min_length=3, max_length=3, pattern='^[A-Z]{3}$')
    isin: str | None = Field(default=None, min_length=12, max_length=12)
    active: bool = True


class AssetRead(AssetCreate):
    id: int


class AssetProviderSymbolCreate(BaseModel):
    asset_id: int = Field(ge=1)
    provider: str = Field(min_length=1, max_length=64)
    provider_symbol: str = Field(min_length=1, max_length=64)


class AssetProviderSymbolRead(AssetProviderSymbolCreate):
    pass


class AssetDiscoverItem(BaseModel):
    key: str
    source: Literal['db', 'provider']
    asset_id: int | None = None
    symbol: str
    name: str | None = None
    exchange: str | None = None
    provider: str | None = None
    provider_symbol: str | None = None


class AssetDiscoverResponse(BaseModel):
    items: list[AssetDiscoverItem]


class AssetEnsureRequest(BaseModel):
    source: Literal['db', 'provider']
    asset_id: int | None = Field(default=None, ge=1)
    symbol: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=255)
    exchange: str | None = Field(default=None, max_length=255)
    provider: str = Field(default='yfinance', min_length=1, max_length=64)
    provider_symbol: str | None = Field(default=None, max_length=64)
    portfolio_id: int | None = Field(default=None, ge=1)


class AssetEnsureResponse(BaseModel):
    asset_id: int
    symbol: str
    created: bool


class Position(BaseModel):
    asset_id: int
    symbol: str
    name: str
    quantity: float
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float
    weight: float
    first_trade_at: datetime | None = None


class PortfolioSummary(BaseModel):
    portfolio_id: int
    base_currency: str
    market_value: float
    cost_basis: float
    unrealized_pl: float
    unrealized_pl_pct: float
    day_change: float = 0.0
    day_change_pct: float = 0.0
    cash_balance: float = 0.0


class TimeSeriesPoint(BaseModel):
    date: str
    market_value: float


class AllocationItem(BaseModel):
    asset_id: int
    symbol: str
    market_value: float
    weight_pct: float


class PortfolioTargetAllocationUpsert(BaseModel):
    asset_id: int = Field(ge=1)
    weight_pct: float = Field(ge=0, le=100)


class PortfolioTargetAllocationItem(BaseModel):
    asset_id: int
    symbol: str
    name: str
    weight_pct: float


class PortfolioTargetPerformancePoint(BaseModel):
    date: str
    weighted_index: float


class PortfolioTargetPerformer(BaseModel):
    asset_id: int
    symbol: str
    name: str
    return_pct: float
    as_of: datetime | None = None


class PortfolioTargetPerformanceResponse(BaseModel):
    portfolio_id: int
    points: list[PortfolioTargetPerformancePoint]
    last_updated_at: datetime | None = None
    best: PortfolioTargetPerformer | None = None
    worst: PortfolioTargetPerformer | None = None


class PortfolioTargetAssetPerformancePoint(BaseModel):
    date: str
    index_value: float


class PortfolioTargetAssetPerformanceSeries(BaseModel):
    asset_id: int
    symbol: str
    name: str
    weight_pct: float
    return_pct: float
    as_of: datetime | None = None
    points: list[PortfolioTargetAssetPerformancePoint]


class PortfolioTargetAssetPerformanceResponse(BaseModel):
    portfolio_id: int
    points_count: int
    assets: list[PortfolioTargetAssetPerformanceSeries]


class PortfolioTargetAssetIntradayPerformancePoint(BaseModel):
    ts: str
    weighted_index: float


class PortfolioTargetAssetIntradayPerformanceSeries(BaseModel):
    asset_id: int
    symbol: str
    name: str
    weight_pct: float
    return_pct: float
    as_of: datetime | None = None
    points: list[PortfolioTargetAssetIntradayPerformancePoint]


class PortfolioTargetAssetIntradayPerformanceResponse(BaseModel):
    portfolio_id: int
    date: str
    assets: list[PortfolioTargetAssetIntradayPerformanceSeries]


class PortfolioTargetIntradayPoint(BaseModel):
    ts: str
    weighted_index: float


class PortfolioTargetIntradayResponse(BaseModel):
    portfolio_id: int
    date: str
    points: list[PortfolioTargetIntradayPoint]


class PriceRefreshItem(BaseModel):
    asset_id: int
    symbol: str
    provider_symbol: str
    price: float
    ts: datetime


class PriceRefreshResponse(BaseModel):
    provider: str
    requested_assets: int
    refreshed_assets: int
    failed_assets: int
    items: list[PriceRefreshItem]
    errors: list[str]


class DailyBackfillItem(BaseModel):
    asset_id: int
    symbol: str
    provider_symbol: str
    bars_saved: int


class FxBackfillItem(BaseModel):
    from_currency: str
    to_currency: str
    rates_saved: int


class DailyBackfillResponse(BaseModel):
    provider: str
    portfolio_id: int
    start_date: date
    end_date: date
    assets_requested: int
    assets_refreshed: int
    fx_pairs_refreshed: int
    asset_items: list[DailyBackfillItem]
    fx_items: list[FxBackfillItem]
    errors: list[str]


class AssetCoverageItem(BaseModel):
    asset_id: int
    symbol: str
    name: str
    bar_count: int
    first_bar: date | None
    last_bar: date | None
    expected_bars: int
    coverage_pct: float


class DataCoverageResponse(BaseModel):
    portfolio_id: int
    days: int
    sufficient: bool
    threshold_pct: float
    assets: list[AssetCoverageItem]


class RebalancePreviewRequest(BaseModel):
    mode: Literal['buy_only', 'rebalance', 'sell_only'] = 'buy_only'
    max_transactions: int = Field(default=5, ge=1, le=100)
    cash_to_allocate: float | None = Field(default=None, ge=0)
    min_order_value: float = Field(default=0, ge=0)
    trade_at: datetime | None = None
    rounding: Literal['fractional', 'integer'] = 'fractional'
    selection_strategy: Literal['largest_drift'] = 'largest_drift'
    use_latest_prices: bool = True


class RebalancePreviewItem(BaseModel):
    asset_id: int
    symbol: str
    name: str
    target_weight_pct: float
    current_weight_pct: float
    drift_pct: float
    current_quantity: float
    side: Literal['buy', 'sell']
    trade_currency: str
    price: float
    quantity: float
    gross_total: float
    tradable: bool = True
    skip_reason: str | None = None


class RebalancePreviewSummary(BaseModel):
    proposed_buy_total: float
    proposed_sell_total: float
    cash_input: float
    estimated_cash_residual: float
    generated_count: int
    skipped_count: int


class RebalancePreviewResponse(BaseModel):
    portfolio_id: int
    base_currency: str
    mode: Literal['buy_only', 'rebalance', 'sell_only']
    trade_at: datetime | None = None
    summary: RebalancePreviewSummary
    items: list[RebalancePreviewItem]
    warnings: list[str]


class RebalanceCommitItemInput(BaseModel):
    asset_id: int = Field(ge=1)
    side: Literal['buy', 'sell']
    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    fees: float = Field(default=0, ge=0)
    taxes: float = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class RebalanceCommitRequest(BaseModel):
    trade_at: datetime
    items: list[RebalanceCommitItemInput] = Field(min_length=1, max_length=200)


class RebalanceCommitCreatedItem(BaseModel):
    transaction_id: int
    asset_id: int
    side: Literal['buy', 'sell']
    quantity: float
    price: float


class RebalanceCommitResponse(BaseModel):
    portfolio_id: int
    requested: int
    created: int
    failed: int
    items: list[RebalanceCommitCreatedItem]
    errors: list[str]


class MarketQuoteItem(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    ts: datetime | None = None
    error: str | None = None


class MarketCategory(BaseModel):
    category: str
    label: str
    items: list[MarketQuoteItem]


class MarketQuotesResponse(BaseModel):
    categories: list[MarketCategory]
