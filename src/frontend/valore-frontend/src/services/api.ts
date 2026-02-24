const API_URL = '/api';

export interface ApiErrorPayload {
  error?: {
    code: string;
    message: string;
  };
}

export interface Portfolio {
  id: number;
  name: string;
  base_currency: string;
  timezone: string;
  target_notional: number | null;
  cash_balance: number;
  created_at: string;
}

export interface PortfolioCreateInput {
  name: string;
  base_currency: string;
  timezone: string;
  target_notional?: number | null;
  cash_balance?: number;
}

export interface PortfolioUpdateInput {
  name?: string;
  base_currency?: string;
  timezone?: string;
  target_notional?: number | null;
  cash_balance?: number;
}

export interface PortfolioSummary {
  portfolio_id: number;
  base_currency: string;
  market_value: number;
  cost_basis: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
  day_change: number;
  day_change_pct: number;
  cash_balance: number;
}

export interface Position {
  asset_id: number;
  symbol: string;
  name: string;
  quantity: number;
  avg_cost: number;
  market_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
  weight: number;
  first_trade_at?: string | null;
}

export interface AllocationItem {
  asset_id: number;
  symbol: string;
  market_value: number;
  weight_pct: number;
}

export interface PortfolioTargetAllocationItem {
  asset_id: number;
  symbol: string;
  name: string;
  weight_pct: number;
}

export interface TimeSeriesPoint {
  date: string;
  market_value: number;
}

export interface PortfolioTargetPerformancePoint {
  date: string;
  weighted_index: number;
}

export interface PortfolioTargetPerformer {
  asset_id: number;
  symbol: string;
  name: string;
  return_pct: number;
  as_of: string | null;
}

export interface PortfolioTargetPerformanceResponse {
  portfolio_id: number;
  points: PortfolioTargetPerformancePoint[];
  last_updated_at: string | null;
  best: PortfolioTargetPerformer | null;
  worst: PortfolioTargetPerformer | null;
}

export interface PortfolioTargetIntradayPoint {
  ts: string;
  weighted_index: number;
}

export interface PortfolioTargetIntradayResponse {
  portfolio_id: number;
  date: string;
  points: PortfolioTargetIntradayPoint[];
}

export interface PortfolioTargetAssetPerformancePoint {
  date: string;
  index_value: number;
}

export interface PortfolioTargetAssetPerformanceSeries {
  asset_id: number;
  symbol: string;
  name: string;
  weight_pct: number;
  return_pct: number;
  as_of: string | null;
  points: PortfolioTargetAssetPerformancePoint[];
}

export interface PortfolioTargetAssetPerformanceResponse {
  portfolio_id: number;
  points_count: number;
  assets: PortfolioTargetAssetPerformanceSeries[];
}

export interface PortfolioTargetAssetIntradayPerformancePoint {
  ts: string;
  weighted_index: number;
}

export interface PortfolioTargetAssetIntradayPerformanceSeries {
  asset_id: number;
  symbol: string;
  name: string;
  weight_pct: number;
  return_pct: number;
  as_of: string | null;
  points: PortfolioTargetAssetIntradayPerformancePoint[];
}

export interface PortfolioTargetAssetIntradayPerformanceResponse {
  portfolio_id: number;
  date: string;
  assets: PortfolioTargetAssetIntradayPerformanceSeries[];
}

export interface PriceRefreshResponse {
  provider: string;
  requested_assets: number;
  refreshed_assets: number;
  failed_assets: number;
  items: Array<{
    asset_id: number;
    symbol: string;
    provider_symbol: string;
    price: number;
    ts: string;
  }>;
  errors: string[];
}

export interface DailyBackfillResponse {
  provider: string;
  portfolio_id: number;
  start_date: string;
  end_date: string;
  assets_requested: number;
  assets_refreshed: number;
  fx_pairs_refreshed: number;
  asset_items: Array<{ asset_id: number; symbol: string; provider_symbol: string; bars_saved: number }>;
  fx_items: Array<{ from_currency: string; to_currency: string; rates_saved: number }>;
  errors: string[];
}

export interface Symbol {
  symbol: string;
  instrument_name: string | null;
  exchange: string | null;
  country: string | null;
}

export interface AssetSearchResult {
  id: string;
  symbol: string;
  name: string;
}

export interface AssetDiscoverItem {
  key: string;
  source: 'db' | 'provider';
  asset_id: number | null;
  symbol: string;
  name: string | null;
  exchange: string | null;
  provider: string | null;
  provider_symbol: string | null;
}

export interface AssetCreateInput {
  symbol: string;
  name?: string | null;
  asset_type: 'stock' | 'etf' | 'crypto' | 'bond' | 'cash' | 'fund';
  exchange_code?: string | null;
  exchange_name?: string | null;
  quote_currency: string;
  isin?: string | null;
  active?: boolean;
}

export interface AssetRead extends AssetCreateInput {
  id: number;
}

export interface AssetProviderSymbolCreateInput {
  asset_id: number;
  provider: string;
  provider_symbol: string;
}

export interface AssetEnsureInput {
  source: 'db' | 'provider';
  asset_id?: number | null;
  symbol: string;
  name?: string | null;
  exchange?: string | null;
  provider?: string;
  provider_symbol?: string | null;
  portfolio_id?: number | null;
}

export interface AssetEnsureResponse {
  asset_id: number;
  symbol: string;
  created: boolean;
}

export interface AssetLatestQuoteResponse {
  asset_id: number;
  symbol: string;
  provider: string;
  provider_symbol: string;
  price: number;
  ts: string;
}

export interface TransactionCreateInput {
  portfolio_id: number;
  asset_id: number;
  side: 'buy' | 'sell';
  trade_at: string;
  quantity: number;
  price: number;
  fees?: number;
  taxes?: number;
  trade_currency: string;
  notes?: string | null;
}

export interface TransactionRead extends TransactionCreateInput {
  id: number;
}

export interface TransactionListItem extends TransactionRead {
  symbol: string;
  asset_name?: string | null;
}

export interface TransactionUpdateInput {
  trade_at?: string;
  quantity?: number;
  price?: number;
  fees?: number;
  taxes?: number;
  notes?: string | null;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorPayload;
      if (body?.error?.message) {
        message = body.error.message;
      }
    } catch {
      const text = await response.text().catch(() => '');
      if (text) {
        message = text;
      }
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export const getAdminPortfolios = async (): Promise<Portfolio[]> => {
  return apiFetch<Portfolio[]>('/admin/portfolios');
};

export const createPortfolio = async (payload: PortfolioCreateInput): Promise<Portfolio> => {
  return apiFetch<Portfolio>('/portfolios', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const updatePortfolio = async (portfolioId: number, payload: PortfolioUpdateInput): Promise<Portfolio> => {
  return apiFetch<Portfolio>(`/portfolios/${portfolioId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
};

export const deletePortfolio = async (portfolioId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/portfolios/${portfolioId}`, {
    method: 'DELETE',
  });
};

export const getPortfolioSummary = async (portfolioId: number): Promise<PortfolioSummary> => {
  return apiFetch<PortfolioSummary>(`/portfolios/${portfolioId}/summary`);
};

export const getPortfolioPositions = async (portfolioId: number): Promise<Position[]> => {
  return apiFetch<Position[]>(`/portfolios/${portfolioId}/positions`);
};

export const getPortfolioAllocation = async (portfolioId: number): Promise<AllocationItem[]> => {
  return apiFetch<AllocationItem[]>(`/portfolios/${portfolioId}/allocation`);
};

export const getPortfolioTimeseries = async (portfolioId: number): Promise<TimeSeriesPoint[]> => {
  return apiFetch<TimeSeriesPoint[]>(`/portfolios/${portfolioId}/timeseries?range=1y&interval=1d`);
};

export const getPortfolioTargetPerformance = async (portfolioId: number): Promise<PortfolioTargetPerformanceResponse> => {
  return apiFetch<PortfolioTargetPerformanceResponse>(`/portfolios/${portfolioId}/target-performance`);
};

export const getPortfolioTargetIntradayPerformance = async (
  portfolioId: number,
  date: string,
): Promise<PortfolioTargetIntradayResponse> => {
  return apiFetch<PortfolioTargetIntradayResponse>(
    `/portfolios/${portfolioId}/target-performance/intraday?date=${encodeURIComponent(date)}`,
  );
};

export const getPortfolioTargetAssetPerformance = async (
  portfolioId: number,
): Promise<PortfolioTargetAssetPerformanceResponse> => {
  return apiFetch<PortfolioTargetAssetPerformanceResponse>(`/portfolios/${portfolioId}/target-performance/assets`);
};

export const getPortfolioTargetAssetIntradayPerformance = async (
  portfolioId: number,
  date: string,
): Promise<PortfolioTargetAssetIntradayPerformanceResponse> => {
  return apiFetch<PortfolioTargetAssetIntradayPerformanceResponse>(
    `/portfolios/${portfolioId}/target-performance/assets/intraday?date=${encodeURIComponent(date)}`,
  );
};

export const refreshPortfolioPrices = async (
  portfolioId: number,
  assetScope: 'target' | 'transactions' | 'all' = 'target',
): Promise<PriceRefreshResponse> => {
  return apiFetch<PriceRefreshResponse>(`/prices/refresh?portfolio_id=${portfolioId}&asset_scope=${assetScope}`, {
    method: 'POST',
  });
};

export const backfillPortfolioDailyPrices = async (
  portfolioId: number,
  days = 365,
  assetScope: 'target' | 'transactions' | 'all' = 'target',
): Promise<DailyBackfillResponse> => {
  return apiFetch<DailyBackfillResponse>(
    `/prices/backfill-daily?portfolio_id=${portfolioId}&days=${days}&asset_scope=${assetScope}`,
    { method: 'POST' },
  );
};

export const getPortfolioTargetAllocation = async (portfolioId: number): Promise<PortfolioTargetAllocationItem[]> => {
  return apiFetch<PortfolioTargetAllocationItem[]>(`/portfolios/${portfolioId}/target-allocation`);
};

export const upsertPortfolioTargetAllocation = async (
  portfolioId: number,
  payload: { asset_id: number; weight_pct: number },
): Promise<PortfolioTargetAllocationItem> => {
  return apiFetch<PortfolioTargetAllocationItem>(`/portfolios/${portfolioId}/target-allocation`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const deletePortfolioTargetAllocation = async (portfolioId: number, assetId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/portfolios/${portfolioId}/target-allocation/${assetId}`, {
    method: 'DELETE',
  });
};

export const getSymbols = async (query: string): Promise<Symbol[]> => {
  const q = query.trim();
  if (!q) {
    return [];
  }
  const payload = await apiFetch<{ symbols: Symbol[] }>(`/symbols?q=${encodeURIComponent(q)}`);
  return payload.symbols ?? [];
};

export const searchAssets = async (query: string): Promise<AssetSearchResult[]> => {
  const q = query.trim();
  if (!q) {
    return [];
  }
  const payload = await apiFetch<{ assets: AssetSearchResult[] }>(`/assets/search?q=${encodeURIComponent(q)}`);
  return payload.assets ?? [];
};

export const discoverAssets = async (query: string): Promise<AssetDiscoverItem[]> => {
  const q = query.trim();
  if (!q) {
    return [];
  }
  const payload = await apiFetch<{ items: AssetDiscoverItem[] }>(`/assets/discover?q=${encodeURIComponent(q)}`);
  return payload.items ?? [];
};

export const createAsset = async (payload: AssetCreateInput): Promise<AssetRead> => {
  return apiFetch<AssetRead>('/assets', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const createAssetProviderSymbol = async (payload: AssetProviderSymbolCreateInput): Promise<AssetProviderSymbolCreateInput> => {
  return apiFetch<AssetProviderSymbolCreateInput>('/asset-provider-symbols', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const ensureAsset = async (payload: AssetEnsureInput): Promise<AssetEnsureResponse> => {
  return apiFetch<AssetEnsureResponse>('/assets/ensure', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getAssetLatestQuote = async (assetId: number): Promise<AssetLatestQuoteResponse> => {
  return apiFetch<AssetLatestQuoteResponse>(`/assets/${assetId}/latest-quote`);
};

export const createTransaction = async (payload: TransactionCreateInput): Promise<TransactionRead> => {
  return apiFetch<TransactionRead>('/transactions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getPortfolioTransactions = async (portfolioId: number): Promise<TransactionListItem[]> => {
  return apiFetch<TransactionListItem[]>(`/portfolios/${portfolioId}/transactions`);
};

export const updateTransaction = async (
  transactionId: number,
  payload: TransactionUpdateInput,
): Promise<TransactionRead> => {
  return apiFetch<TransactionRead>(`/transactions/${transactionId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
};

export const deleteTransaction = async (transactionId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/transactions/${transactionId}`, {
    method: 'DELETE',
  });
};
