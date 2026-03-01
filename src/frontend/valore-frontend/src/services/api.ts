const API_URL = import.meta.env.VITE_API_BASE_URL || '/api';

type TokenGetter = () => Promise<string | null>;
let _getToken: TokenGetter = async () => null;
export function setTokenGetter(fn: TokenGetter): void {
  _getToken = fn;
}

export interface ApiErrorPayload {
  error?: {
    code: string;
    message: string;
  };
}

export interface UserSettings {
  user_id: string;
  broker_default_fee: number;
}

export interface UserSettingsUpdateInput {
  broker_default_fee: number;
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

export interface PortfolioCloneInput {
  name?: string | null;
}

export interface PortfolioCloneResponse {
  portfolio: Portfolio;
  target_allocations_copied: number;
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
  supports_fractions?: boolean;
}

export interface AssetRead extends AssetCreateInput {
  id: number;
  supports_fractions: boolean;
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

export type TransactionSide = 'buy' | 'sell' | 'deposit' | 'withdrawal' | 'dividend' | 'fee' | 'interest';

export interface TransactionCreateInput {
  portfolio_id: number;
  asset_id?: number | null;
  side: TransactionSide;
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
  symbol?: string | null;
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

export interface AssetCoverageItem {
  asset_id: number;
  symbol: string;
  name: string;
  bar_count: number;
  first_bar: string | null;
  last_bar: string | null;
  expected_bars: number;
  coverage_pct: number;
}

export interface DataCoverageResponse {
  portfolio_id: number;
  days: number;
  sufficient: boolean;
  threshold_pct: number;
  assets: AssetCoverageItem[];
}

export interface RebalancePreviewInput {
  mode: 'buy_only' | 'rebalance' | 'sell_only';
  max_transactions: number;
  cash_to_allocate?: number | null;
  min_order_value?: number;
  trade_at?: string | null;
  rounding: 'fractional' | 'integer';
  selection_strategy?: 'largest_drift';
  use_latest_prices?: boolean;
}

export interface RebalancePreviewItem {
  asset_id: number;
  symbol: string;
  name: string;
  target_weight_pct: number;
  current_weight_pct: number;
  drift_pct: number;
  current_quantity: number;
  side: 'buy' | 'sell';
  trade_currency: string;
  price: number;
  quantity: number;
  gross_total: number;
  tradable: boolean;
  skip_reason: string | null;
}

export interface RebalancePreviewSummary {
  proposed_buy_total: number;
  proposed_sell_total: number;
  cash_input: number;
  estimated_cash_residual: number;
  generated_count: number;
  skipped_count: number;
}

export interface RebalancePreviewResponse {
  portfolio_id: number;
  base_currency: string;
  mode: 'buy_only' | 'rebalance' | 'sell_only';
  trade_at: string | null;
  summary: RebalancePreviewSummary;
  items: RebalancePreviewItem[];
  warnings: string[];
}

export interface RebalanceCommitItemInput {
  asset_id: number;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  fees?: number;
  taxes?: number;
  notes?: string | null;
}

export interface RebalanceCommitInput {
  trade_at: string;
  items: RebalanceCommitItemInput[];
}

export interface RebalanceCommitCreatedItem {
  transaction_id: number;
  asset_id: number;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
}

export interface RebalanceCommitResponse {
  portfolio_id: number;
  requested: number;
  created: number;
  failed: number;
  items: RebalanceCommitCreatedItem[];
  errors: string[];
}

export interface MarketQuoteItem {
  symbol: string;
  name: string;
  price: number | null;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  ts: string | null;
  error: string | null;
}

export interface MarketCategory {
  category: string;
  label: string;
  items: MarketQuoteItem[];
}

export interface MarketQuotesResponse {
  categories: MarketCategory[];
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await _getToken();
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${API_URL}${path}`, {
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
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

export const getPortfolios = async (): Promise<Portfolio[]> => {
  return apiFetch<Portfolio[]>('/portfolios');
};

/** @deprecated Use getPortfolios instead */
export const getAdminPortfolios = getPortfolios;

export const getUserSettings = async (): Promise<UserSettings> => {
  return apiFetch<UserSettings>('/settings/user');
};

export const updateUserSettings = async (payload: UserSettingsUpdateInput): Promise<UserSettings> => {
  return apiFetch<UserSettings>('/settings/user', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
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

export const clonePortfolio = async (portfolioId: number, payload: PortfolioCloneInput): Promise<PortfolioCloneResponse> => {
  return apiFetch<PortfolioCloneResponse>(`/portfolios/${portfolioId}/clone`, {
    method: 'POST',
    body: JSON.stringify(payload),
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

export const getMarketQuotes = async (): Promise<MarketQuotesResponse> => {
  return apiFetch<MarketQuotesResponse>('/markets/quotes');
};

export const getPortfolioDataCoverage = async (
  portfolioId: number,
  days = 365,
  thresholdPct = 80,
): Promise<DataCoverageResponse> => {
  return apiFetch<DataCoverageResponse>(
    `/portfolios/${portfolioId}/data-coverage?days=${days}&threshold_pct=${thresholdPct}`,
  );
};

export const getPortfolioRebalancePreview = async (
  portfolioId: number,
  payload: RebalancePreviewInput,
): Promise<RebalancePreviewResponse> => {
  return apiFetch<RebalancePreviewResponse>(`/portfolios/${portfolioId}/rebalance/preview`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const commitPortfolioRebalance = async (
  portfolioId: number,
  payload: RebalanceCommitInput,
): Promise<RebalanceCommitResponse> => {
  return apiFetch<RebalanceCommitResponse>(`/portfolios/${portfolioId}/rebalance/commit`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

// ---- Feature 2: Cash Movements ----

export interface CashMovementCreateInput {
  portfolio_id: number;
  side: 'deposit' | 'withdrawal' | 'dividend' | 'fee' | 'interest';
  trade_at: string;
  quantity: number;
  trade_currency: string;
  asset_id?: number | null;
  notes?: string | null;
}

export interface CashCurrencyBreakdown {
  currency: string;
  balance: number;
}

export interface CashBalanceResponse {
  portfolio_id: number;
  total_cash: number;
  currency_breakdown: CashCurrencyBreakdown[];
  recent_movements: TransactionListItem[];
}

export interface CashFlowTimelinePoint {
  date: string;
  cumulative_cash: number;
  deposits: number;
  withdrawals: number;
  dividends: number;
  fees: number;
  interest: number;
}

export interface CashFlowTimelineResponse {
  portfolio_id: number;
  points: CashFlowTimelinePoint[];
}

export const createCashMovement = async (payload: CashMovementCreateInput): Promise<TransactionRead> => {
  return apiFetch<TransactionRead>('/cash-movements', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getPortfolioCashBalance = async (portfolioId: number): Promise<CashBalanceResponse> => {
  return apiFetch<CashBalanceResponse>(`/portfolios/${portfolioId}/cash-balance`);
};

export const getPortfolioCashFlowTimeline = async (portfolioId: number): Promise<CashFlowTimelineResponse> => {
  return apiFetch<CashFlowTimelineResponse>(`/portfolios/${portfolioId}/cash-flow-timeline`);
};

// ---- Feature 3: CSV Import ----

export interface CsvImportPreviewRow {
  row_number: number;
  valid: boolean;
  errors: string[];
  trade_at: string | null;
  symbol: string | null;
  side: string | null;
  quantity: number | null;
  price: number | null;
  fees: number | null;
  taxes: number | null;
  trade_currency: string | null;
  notes: string | null;
  asset_id: number | null;
  asset_name: string | null;
}

export interface CsvImportPreviewResponse {
  batch_id: number;
  filename: string | null;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  rows: CsvImportPreviewRow[];
}

export interface CsvImportCommitResponse {
  batch_id: number;
  committed_transactions: number;
  errors: string[];
}

export const uploadCsvImportPreview = async (
  portfolioId: number,
  file: File,
): Promise<CsvImportPreviewResponse> => {
  const token = await _getToken();
  const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_URL}/portfolios/${portfolioId}/csv-import/preview`, {
    method: 'POST',
    headers: { ...authHeaders },
    body: formData,
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as ApiErrorPayload;
      if (body?.error?.message) message = body.error.message;
    } catch { /* ignore */ }
    throw new Error(message);
  }
  return response.json() as Promise<CsvImportPreviewResponse>;
};

export const commitCsvImport = async (batchId: number): Promise<CsvImportCommitResponse> => {
  return apiFetch<CsvImportCommitResponse>(`/csv-import/${batchId}/commit`, {
    method: 'POST',
  });
};

export const cancelCsvImport = async (batchId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/csv-import/${batchId}`, {
    method: 'DELETE',
  });
};

// ---- Feature 4: PAC ----

export interface PacRuleCreateInput {
  portfolio_id: number;
  asset_id: number;
  mode: 'amount' | 'quantity';
  amount?: number | null;
  quantity?: number | null;
  frequency: 'weekly' | 'biweekly' | 'monthly';
  day_of_month?: number | null;
  day_of_week?: number | null;
  start_date: string;
  end_date?: string | null;
  auto_execute?: boolean;
}

export interface PacRuleRead {
  id: number;
  portfolio_id: number;
  asset_id: number;
  symbol: string | null;
  asset_name: string | null;
  mode: 'amount' | 'quantity';
  amount: number | null;
  quantity: number | null;
  frequency: 'weekly' | 'biweekly' | 'monthly';
  day_of_month: number | null;
  day_of_week: number | null;
  start_date: string;
  end_date: string | null;
  auto_execute: boolean;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PacRuleUpdateInput {
  mode?: 'amount' | 'quantity';
  amount?: number | null;
  quantity?: number | null;
  frequency?: 'weekly' | 'biweekly' | 'monthly';
  day_of_month?: number | null;
  day_of_week?: number | null;
  end_date?: string | null;
  auto_execute?: boolean;
  active?: boolean;
}

export interface PacExecutionRead {
  id: number;
  pac_rule_id: number;
  scheduled_date: string;
  status: 'pending' | 'executed' | 'skipped' | 'failed';
  transaction_id: number | null;
  executed_price: number | null;
  executed_quantity: number | null;
  error_message: string | null;
  created_at: string;
  executed_at: string | null;
}

export interface PacExecutionConfirmInput {
  price: number;
  trade_currency: string;
  fees?: number;
  taxes?: number;
  notes?: string | null;
}

export const createPacRule = async (portfolioId: number, payload: PacRuleCreateInput): Promise<PacRuleRead> => {
  return apiFetch<PacRuleRead>(`/portfolios/${portfolioId}/pac-rules`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const getPortfolioPacRules = async (portfolioId: number): Promise<PacRuleRead[]> => {
  return apiFetch<PacRuleRead[]>(`/portfolios/${portfolioId}/pac-rules`);
};

export const getPacRule = async (ruleId: number): Promise<PacRuleRead> => {
  return apiFetch<PacRuleRead>(`/pac-rules/${ruleId}`);
};

export const updatePacRule = async (ruleId: number, payload: PacRuleUpdateInput): Promise<PacRuleRead> => {
  return apiFetch<PacRuleRead>(`/pac-rules/${ruleId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
};

export const deletePacRule = async (ruleId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/pac-rules/${ruleId}`, {
    method: 'DELETE',
  });
};

export const getPacRuleExecutions = async (ruleId: number): Promise<PacExecutionRead[]> => {
  return apiFetch<PacExecutionRead[]>(`/pac-rules/${ruleId}/executions`);
};

export const getPendingPacExecutions = async (portfolioId: number): Promise<PacExecutionRead[]> => {
  return apiFetch<PacExecutionRead[]>(`/portfolios/${portfolioId}/pac-executions/pending`);
};

export const confirmPacExecution = async (
  executionId: number,
  payload: PacExecutionConfirmInput,
): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/pac-executions/${executionId}/confirm`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
};

export const skipPacExecution = async (executionId: number): Promise<{ status: string }> => {
  return apiFetch<{ status: string }>(`/pac-executions/${executionId}/skip`, {
    method: 'POST',
  });
};
