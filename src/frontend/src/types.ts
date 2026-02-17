export type PortfolioSummary = {
  portfolio_id: number;
  base_currency: string;
  market_value: number;
  cost_basis: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
};

export type Position = {
  asset_id: number;
  symbol: string;
  quantity: number;
  avg_cost: number;
  market_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
};

export type TimeSeriesPoint = {
  date: string;
  market_value: number;
};

export type AssetType = "stock" | "etf" | "crypto" | "bond" | "cash" | "fund";

export type AssetCreateRequest = {
  symbol: string;
  name?: string;
  asset_type: AssetType;
  exchange_code?: string;
  exchange_name?: string;
  quote_currency: string;
  isin?: string;
  active: boolean;
};

export type AssetRead = AssetCreateRequest & {
  id: number;
};

export type AssetProviderSymbolCreateRequest = {
  asset_id: number;
  provider: string;
  provider_symbol: string;
};

export type AssetSearchItem = {
  id: string;
  symbol: string;
  name: string;
};

export type TransactionCreateRequest = {
  portfolio_id: number;
  asset_id: number;
  side: "buy" | "sell";
  trade_at: string;
  quantity: number;
  price: number;
  fees: number;
  taxes: number;
  trade_currency: string;
  notes?: string;
};

export type PriceRefreshResponse = {
  provider: string;
  requested_assets: number;
  refreshed_assets: number;
  failed_assets: number;
  errors: string[];
};

export type DailyBackfillResponse = {
  provider: string;
  portfolio_id: number;
  start_date: string;
  end_date: string;
  assets_requested: number;
  assets_refreshed: number;
  fx_pairs_refreshed: number;
  errors: string[];
};
