from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ApiError


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


class Position(BaseModel):
    asset_id: int
    symbol: str
    quantity: float
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float


class PortfolioSummary(BaseModel):
    portfolio_id: int
    base_currency: str
    market_value: float
    cost_basis: float
    unrealized_pl: float
    unrealized_pl_pct: float


class TimeSeriesPoint(BaseModel):
    date: str
    market_value: float


class AllocationItem(BaseModel):
    asset_id: int
    symbol: str
    market_value: float
    weight_pct: float


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
