export interface InstantAnalyzeRequest {
  input_mode: 'text' | 'raw_text';
  positions?: Array<{
    identifier: string;
    value: number;
  }>;
  raw_text?: string;
}

export interface InstantAnalyzeLineError {
  line: number;
  raw: string;
  error: string;
}

export interface InstantAnalyzeUnresolvedItem {
  identifier: string;
  raw: string | null;
  line: number | null;
  error: string;
}

export interface PortfolioAnalyzeSummary {
  total_value: number;
  score: number;
  risk_level: 'low' | 'medium' | 'high' | 'unknown';
  diversification: 'excellent' | 'good' | 'moderate' | 'weak' | 'unknown';
  overlap: 'low' | 'moderate' | 'high' | 'unknown';
  cost_efficiency: 'low_cost' | 'moderate_cost' | 'high_cost' | 'unknown';
}

export interface PortfolioAnalyzeMetrics {
  geographic_exposure: Record<string, number>;
  asset_allocation: Record<string, number>;
  max_position_weight: number;
  overlap_score: number;
  portfolio_volatility: number | null;
  weighted_ter: number | null;
  risk_score: number;
  estimated_drawdown: number;
}

export interface ResolvedPublicPosition {
  identifier: string;
  resolved_symbol: string;
  resolved_name: string;
  value: number;
  weight: number;
  status: 'resolved';
}

export interface PortfolioAnalyzeAlert {
  severity: 'info' | 'warning' | 'critical';
  code: string;
  message: string;
}

export interface PortfolioAnalyzeSuggestion {
  code: string;
  message: string;
}

export interface InstantAnalyzeCta {
  show_signup: boolean;
  message: string;
}

export interface PortfolioTopInsight {
  id: string;
  type: 'geo_concentration' | 'holding_overlap' | 'portfolio_risk';
  severity: 'medium' | 'high';
  score: number;
  title: string;
  short_description: string;
  explanation_data: Record<string, unknown>;
  cta_label: string;
}

export interface InstantAnalyzeResponse {
  summary: PortfolioAnalyzeSummary;
  positions: ResolvedPublicPosition[];
  unresolved: InstantAnalyzeUnresolvedItem[];
  parse_errors: InstantAnalyzeLineError[];
  metrics: PortfolioAnalyzeMetrics;
  category_scores: PortfolioHealthCategoryScores;
  alerts: PortfolioAnalyzeAlert[];
  suggestions: PortfolioAnalyzeSuggestion[];
  insights: PortfolioTopInsight[];
  cta: InstantAnalyzeCta;
}

export interface InstantInsightExplainRequest {
  insight: PortfolioTopInsight;
}

export interface InstantInsightExplainResponse {
  insight_id: string;
  explanation: string;
  source: 'ai';
}

export interface InstantImportedPosition {
  identifier: string;
  value: number;
  label: string | null;
  line: number | null;
}

export interface InstantPortfolioImportResponse {
  filename: string | null;
  broker: string;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  positions: InstantImportedPosition[];
  parse_errors: InstantAnalyzeLineError[];
  raw_text: string;
}

export interface FireOneOffExpense {
  age: number;
  amount: number;
  label: string;
}

export interface UserSettings {
  user_id: string;
  broker_default_fee: number;
  copilot_provider: string;
  copilot_model: string;
  copilot_api_key_set: boolean;
  fire_annual_expenses: number;
  fire_annual_contribution: number;
  fire_expected_return_pct: number;
  fire_safe_withdrawal_rate: number;
  fire_capital_gains_tax_rate: number;
  fire_current_age: number | null;
  fire_target_age: number | null;
  fire_capital_floor: number;
  fire_contribution_growth_pct: number;
  fire_pension_annual: number;
  fire_pension_start_age: number | null;
  fire_one_off_expenses: FireOneOffExpense[];
  fire_terminal_target_min: number;
  fire_terminal_target_max: number;
}

export interface UserSettingsUpdateInput {
  broker_default_fee?: number;
  copilot_provider?: string;
  copilot_model?: string;
  copilot_api_key?: string;
  fire_annual_expenses?: number;
  fire_annual_contribution?: number;
  fire_expected_return_pct?: number;
  fire_safe_withdrawal_rate?: number;
  fire_capital_gains_tax_rate?: number;
  fire_current_age?: number | null;
  fire_target_age?: number | null;
  fire_capital_floor?: number;
  fire_contribution_growth_pct?: number;
  fire_pension_annual?: number;
  fire_pension_start_age?: number | null;
  fire_one_off_expenses?: FireOneOffExpense[];
  fire_terminal_target_min?: number;
  fire_terminal_target_max?: number;
}

export interface AdminUsageSummary {
  registered_users: number;
  users_with_portfolios: number;
  users_with_transactions: number;
  users_with_imports: number;
  portfolios_total: number;
  transactions_total: number;
  csv_import_batches_total: number;
  portfolios_created_7d: number;
  imports_started_7d: number;
  analyzer_runs_total: number;
  analyzer_runs_7d: number;
  analyzer_unique_visitors_7d: number;
  public_instant_analyzer_tracked: boolean;
}

export interface Portfolio {
  id: number;
  name: string;
  base_currency: string;
  timezone: string;
  target_notional: number | null;
  cash_balance: number;
  current_cash_balance?: number | null;
  created_at: string;
}

export interface PortfolioHealthSummary {
  risk_level: 'low' | 'medium' | 'high' | 'unknown';
  diversification: 'excellent' | 'good' | 'moderate' | 'weak' | 'unknown';
  overlap: 'low' | 'moderate' | 'high' | 'unknown';
  cost_efficiency: 'low_cost' | 'moderate_cost' | 'high_cost' | 'unknown';
}

export interface PortfolioHealthMetrics {
  geographic_exposure: Record<string, number>;
  sector_exposure: Record<string, number>;
  max_position_weight: number;
  overlap_score: number;
  portfolio_volatility: number | null;
  weighted_ter: number | null;
}

export interface PortfolioHealthCategoryScores {
  diversification: number;
  risk: number;
  concentration: number;
  overlap: number;
  cost_efficiency: number;
}

export interface PortfolioHealthAlert {
  severity: 'info' | 'warning' | 'critical';
  type: string;
  message: string;
  details?: Record<string, unknown> | null;
  education?: PortfolioHealthEducation | null;
}

export interface PortfolioHealthEducation {
  code: string;
  title: string;
  what_it_means: string;
  why_it_matters: string;
  how_to_read_it: string;
  concept: string;
  copilot_prompts: string[];
}

export interface PortfolioHealthSuggestion {
  priority: 'low' | 'medium' | 'high';
  message: string;
}

export interface PortfolioHealthResponse {
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  score: number;
  summary: PortfolioHealthSummary;
  metrics: PortfolioHealthMetrics;
  category_scores: PortfolioHealthCategoryScores;
  alerts: PortfolioHealthAlert[];
  suggestions: PortfolioHealthSuggestion[];
}

export interface MonteCarloYearProjection {
  year: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

export interface MonteCarloProjectionResponse {
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  num_simulations: number;
  horizons: number[];
  projections: MonteCarloYearProjection[];
  annualized_mean_return_pct: number;
  annualized_volatility_pct: number;
}

export interface DecumulationYearProjection {
  year: number;
  age: number | null;
  target_net_spending: number;
  gross_withdrawal: number;
  estimated_taxes: number;
  net_withdrawal: number;
  other_income: number;
  net_spending_after_tax: number;
  p25_ending_capital: number;
  p50_ending_capital: number;
  p75_ending_capital: number;
  p50_effective_withdrawal_rate_pct: number;
  depletion_probability_pct: number;
  capital_floor: number;
  floor_breach_probability_pct: number;
}

export interface DecumulationPlanResponse {
  portfolio_id: number;
  initial_capital: number;
  annual_withdrawal: number;
  annual_other_income: number;
  inflation_rate_pct: number;
  capital_gains_tax_rate_pct: number;
  estimated_embedded_gain_ratio_pct: number;
  horizon_years: number;
  capital_floor: number;
  pension_annual: number;
  pension_start_year: number | null;
  num_simulations: number;
  annualized_mean_return_pct: number;
  annualized_volatility_pct: number;
  sustainable_withdrawal: number;
  success_rate_pct: number;
  depletion_probability_pct: number;
  floor_breach_probability_pct: number;
  p25_terminal_value: number;
  p50_terminal_value: number;
  p75_terminal_value: number;
  depletion_year_p50: number | null;
  floor_breach_year_p50: number | null;
  p50_terminal_value_real: number;
  terminal_target_min: number;
  terminal_target_max: number;
  terminal_below_range_probability_pct: number | null;
  terminal_in_range_probability_pct: number | null;
  terminal_above_range_probability_pct: number | null;
  withdrawal_for_terminal_max: number | null;
  projections: DecumulationYearProjection[];
}

export interface AggregateDecumulationPlanResponse {
  portfolio_ids: number[];
  base_currency: string;
  initial_capital: number;
  annual_withdrawal: number;
  annual_other_income: number;
  inflation_rate_pct: number;
  capital_gains_tax_rate_pct: number;
  estimated_embedded_gain_ratio_pct: number;
  horizon_years: number;
  capital_floor: number;
  pension_annual: number;
  pension_start_year: number | null;
  num_simulations: number;
  annualized_mean_return_pct: number;
  annualized_volatility_pct: number;
  sustainable_withdrawal: number;
  success_rate_pct: number;
  depletion_probability_pct: number;
  floor_breach_probability_pct: number;
  p25_terminal_value: number;
  p50_terminal_value: number;
  p75_terminal_value: number;
  depletion_year_p50: number | null;
  floor_breach_year_p50: number | null;
  p50_terminal_value_real: number;
  terminal_target_min: number;
  terminal_target_max: number;
  terminal_below_range_probability_pct: number | null;
  terminal_in_range_probability_pct: number | null;
  terminal_above_range_probability_pct: number | null;
  withdrawal_for_terminal_max: number | null;
  projections: DecumulationYearProjection[];
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
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  base_currency: string;
  market_value: number;
  cost_basis: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
  day_change: number;
  day_change_pct: number;
  cash_balance: number;
  /** TASK-47: currencies without FX rate (amounts converted at 1.0). */
  fx_missing_currencies?: string[];
  /** TASK-47: positions valued at average cost (no price or no FX). */
  price_fallback_symbols?: string[];
  /** TASK-53: positions whose price is stale (N completed sessions without a new close). */
  stale_price_symbols?: string[];
  /**
   * TASK-49: cash_balance follows the performance cash model (buys debit,
   * sells credit, never negative); cumulative implicit contributions that
   * covered buys/outflows beyond the cash available.
   */
  implicit_contributions_total?: number;
}

export interface TWRResult {
  twr_pct: number | null;
  twr_annualized_pct: number | null;
  period_days: number;
  start_date: string;
  end_date: string;
}

export interface MWRResult {
  mwr_pct: number | null;
  mwr_annualized_pct: number | null;
  period_days: number;
  start_date: string;
  end_date: string;
  converged: boolean;
}

export interface PerformanceSummary {
  period: string;
  period_label: string;
  start_date: string;
  end_date: string;
  period_days: number;
  twr: TWRResult;
  mwr: MWRResult;
  total_deposits: number;
  total_withdrawals: number;
  net_invested: number;
  initial_value: number | null;
  current_value: number;
  absolute_gain: number | null;
}

export interface TWRTimeseriesPoint {
  date: string;
  cumulative_twr_pct: number;
  portfolio_value: number;
}

export interface GainTimeseriesPoint {
  date: string;
  portfolio_value: number;
  net_invested: number;
  absolute_gain: number;
}

export interface MWRTimeseriesPoint {
  date: string;
  cumulative_mwr_pct: number | null;
}

export interface PeriodPerformer {
  asset_id: number;
  symbol: string;
  name: string;
  return_pct: number;
  start_date: string | null;
}

export interface Position {
  asset_id: number;
  symbol: string;
  name: string;
  asset_type: string;
  investment_focus?: string | null;
  quantity: number;
  avg_cost: number;
  market_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
  day_change_pct: number;
  /** false: no previous close, day_change_pct is the 0 default (not a flat day). */
  previous_close_available?: boolean;
  weight: number;
  first_trade_at?: string | null;
  price_stale?: boolean;
  price_date?: string | null;
  /** TASK-53: why price_stale is set, e.g. "ultima quotazione del 30/10, 2 sedute fa". */
  stale_reason?: string | null;
  /** TASK-53: timestamp of the latest provider tick. */
  last_price_at?: string | null;
  /** TASK-47: 'avg_cost' when market_price is the average cost (no price or no FX). */
  price_fallback?: 'avg_cost' | null;
  fx_missing?: boolean;
  fx_missing_currencies?: string[];
}

export interface AssetInfoPricePoint {
  date: string;
  close: number;
}

export interface AssetInfo {
  asset_id: number;
  symbol: string;
  name: string | null;
  asset_type: string | null;
  quote_type: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  market_cap: number | null;
  trailing_pe: number | null;
  forward_pe: number | null;
  dividend_yield: number | null; // percentage points (6.34 = 6.34%)
  beta: number | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;
  avg_volume: number | null;
  currency: string | null;
  current_price: number | null;
  previous_close: number | null;
  day_change_pct: number | null;
  description: string | null;
  price_history_5y: AssetInfoPricePoint[];
  expense_ratio: number | null;
  fund_family: string | null;
  total_assets: number | null;
  category: string | null;
  dividend_rate: number | null;
  profit_margins: number | null;
  return_on_equity: number | null;
  revenue_growth: number | null;
  earnings_growth: number | null;
  website: string | null;
  current_price_source: string | null;
  metadata_status: string;
  price_history_status: string;
  warnings: string[];
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

export interface IntradayTimeseriesPoint {
  ts: string;
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
  /** TASK-53: quotes whose market timestamp did not advance while the market was open. */
  unchanged_ts_symbols?: string[];
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
  isin?: string | null;
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
  quote_source: string | null;
  is_realtime: boolean;
  is_fallback: boolean;
  stale: boolean;
  warning: string | null;
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
  /** Only in aggregate views. */
  portfolio_name?: string | null;
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
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
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

export interface MarketIntradayPoint {
  time: string;
  price: number;
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
  intraday: MarketIntradayPoint[];
  price_source: string | null;
  is_realtime: boolean;
  is_fallback: boolean;
  stale: boolean;
  warning: string | null;
}

export interface MarketCategory {
  category: string;
  label: string;
  items: MarketQuoteItem[];
}

export interface MarketQuotesResponse {
  categories: MarketCategory[];
}

// X-Ray (ETF look-through)

export interface XRayHolding {
  symbol: string;
  name: string;
  aggregated_weight_pct: number;
  etf_contributors: string[];
}

export interface XRayEtfDetail {
  asset_id?: number | null;
  symbol: string;
  name: string;
  investment_focus?: string | null;
  portfolio_weight_pct: number;
  holdings_available: boolean;
  holdings_source: 'justetf' | 'yfinance' | 'missing';
  failure_reason: string | null;
  top_holdings: XRayHolding[];
  /** fund | direct_stock (its own underlying) | no_lookthrough (gold/commodity/crypto) | missing. */
  lookthrough_kind?: 'fund' | 'direct_stock' | 'no_lookthrough' | 'missing';
  /** TASK-52: available | not_applicable (gold, commodity, bond, money market, crypto) | missing (data absent). */
  lookthrough_status?: XRayLookthroughStatus;
  /** Italian reason of lookthrough_status. */
  lookthrough_reason?: string | null;
  /** Sum of the listed top-holding weights, in % of the fund. */
  listed_holdings_pct?: number | null;
  data_source?: 'justetf' | 'yahoo' | 'none';
  /** ISO date of the provider data used for this position. */
  data_as_of?: string | null;
  data_as_of_basis?: 'holdings_date' | 'fetched_at' | 'fetch_time' | null;
}

export type XRayLookthroughStatus = 'available' | 'not_applicable' | 'missing';

export interface XRayCoverageIssue {
  asset_id: number;
  symbol: string;
  name: string;
  reason: string;
  /** TASK-52: not_applicable positions are listed too, but they are not missing data. */
  lookthrough_status?: XRayLookthroughStatus;
  lookthrough_reason?: string | null;
}

export interface XRayResponse {
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  aggregated_holdings: XRayHolding[];
  etf_details: XRayEtfDetail[];
  etf_count: number;
  /** Legacy: weight of funds with at least one top holding (= funds_with_holdings_pct). */
  coverage_pct: number;
  /** Share of the portfolio (cash excluded) actually decomposed into underlying holdings. */
  lookthrough_coverage_pct?: number;
  /** TASK-52: decomposed share of the applicable (equity) part; null when nothing is applicable. */
  applicable_lookthrough_coverage_pct?: number | null;
  /** Shares of coverage_denominator by lookthrough_status (sum to 100). */
  available_pct?: number;
  not_applicable_pct?: number;
  missing_pct?: number;
  applicable_denominator?: string;
  funds_with_holdings_pct?: number;
  classified_country_pct?: number;
  classified_sector_pct?: number;
  unclassified_country_pct?: number;
  unclassified_sector_pct?: number;
  coverage_denominator?: string;
  coverage_note?: string;
  /** Oldest ISO date of the provider data used. */
  data_as_of?: string | null;
  /** Sum to 100 over coverage_denominator, with a "Non classificato" bucket. */
  aggregated_country_exposure: Record<string, number>;
  aggregated_sector_exposure: Record<string, number>;
  coverage_issues: XRayCoverageIssue[];
}

// Stress Test

export interface StressTestAssetImpact {
  symbol: string;
  name: string;
  weight_pct: number;
  estimated_loss_pct: number;
  /** Shared asset class (shock scenarios only). */
  asset_class?: string | null;
}

export interface StressTestClassImpact {
  asset_class: string;
  weight_pct: number;
  /** Shock scenarios: base shock of the class. */
  shock_pct?: number | null;
  /** Historical scenarios: return of the class over the window (real or proxy). */
  drawdown_pct?: number | null;
  /** Historical scenarios: real prices or USD class proxy. */
  source?: 'historical' | 'proxy' | null;
  /** weight x applied shock/drawdown, in portfolio percentage points. */
  contribution_pct: number;
}

export type StressTestMethod = 'historical' | 'proxy' | 'not_available';

export interface StressTestScenarioResult {
  scenario_id: string;
  scenario_name: string;
  scenario_type: 'historical' | 'shock';
  period: string | null;
  estimated_portfolio_impact_pct: number;
  max_drawdown_pct: number | null;
  recovery_months: number | null;
  benchmark_drawdown_pct: number | null;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  most_impacted_assets: StressTestAssetImpact[];
  /** Historical scenarios only: real prices, USD class proxies or empty portfolio. */
  method?: StressTestMethod | null;
  /** Historical scenarios: % of the weight with real prices in the window. */
  coverage_pct?: number | null;
  /** Historical scenarios: Italian note when USD class proxies are used (FX not modelled). */
  methodology_note?: string | null;
  affected_classes?: string[];
  class_breakdown?: StressTestClassImpact[];
  flags?: string[];
}

export interface StressTestResponse {
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  scenarios: StressTestScenarioResult[];
  portfolio_volatility_pct: number | null;
  analysis_date: string;
}

// Market News

export interface MarketNewsItem {
  title: string;
  publisher: string | null;
  link: string | null;
  published: string | null;
  related_symbol: string | null;
  region: string | null;
  summary: string | null;
}

export interface MarketNewsResponse {
  items: MarketNewsItem[];
}

// Market Calendar (upcoming events)

export type MarketCalendarCategory = 'central_bank' | 'earnings' | 'macro';

export interface MarketCalendarEvent {
  id: string;
  category: MarketCalendarCategory;
  importance: 'high' | 'medium';
  title: string;
  description: string | null;
  day: string;
  starts_at: string | null;
  time_hint: string | null;
  region: string | null;
  tags: string[];
  symbol: string | null;
  company: string | null;
  market_cap: number | null;
  eps_estimate: number | null;
  eps_actual: number | null;
  source_name: string | null;
  period: string | null;
  expected: number | null;
  previous: number | null;
  actual: number | null;
}

export interface MarketCalendarDay {
  day: string;
  events: MarketCalendarEvent[];
}

export interface MarketCalendarResponse {
  start_date: string;
  end_date: string;
  timezone: string;
  days: MarketCalendarDay[];
  warnings: string[];
  generated_at: string;
}

// ETF Enrichment

export interface EtfEnrichmentWeight {
  name: string;
  percentage: number;
}

export interface EtfEnrichmentHolding {
  name?: string;
  percentage?: number;
  isin?: string;
}

export interface EtfEnrichment {
  asset_id: number;
  isin: string;
  name: string | null;
  description: string | null;
  index_tracked: string | null;
  investment_focus: string | null;
  country_weights: EtfEnrichmentWeight[] | null;
  sector_weights: EtfEnrichmentWeight[] | null;
  top_holdings: EtfEnrichmentHolding[] | null;
  holdings_date: string | null;
  replication_method: string | null;
  distribution_policy: string | null;
  distribution_frequency: string | null;
  fund_currency: string | null;
  currency_hedged: boolean | null;
  domicile: string | null;
  fund_provider: string | null;
  fund_size_eur: number | null;
  ter: number | null;
  volatility_1y: number | null;
  sustainability: boolean | null;
  inception_date: string | null;
  source: string | null;
  fetched_at: string | null;
}

// Cash

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

/**
 * TASK-49: components of total_cash in base currency (all positive):
 * total_cash = opening_balance + deposits - withdrawals + dividends + interest
 *   - fees - buys + sells + implicit_contributions.
 */
export interface CashBreakdown {
  opening_balance: number;
  deposits: number;
  withdrawals: number;
  dividends: number;
  interest: number;
  fees: number;
  buys: number;
  sells: number;
  implicit_contributions: number;
}

export interface CashBalanceResponse {
  portfolio_id: number;
  total_cash: number;
  currency_breakdown: CashCurrencyBreakdown[];
  recent_movements: TransactionListItem[];
  /** TASK-47: currencies converted at 1.0 for lack of a trade-date FX rate. */
  fx_missing_currencies?: string[];
  /** TASK-49: cumulative implicit contributions (money not recorded as a deposit). */
  implicit_contributions_total?: number;
  cash_breakdown?: CashBreakdown | null;
  /** TASK-49: Italian explanation of the cash model. */
  cash_model_note?: string | null;
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

// CSV Import

export interface CsvImportPreviewRow {
  row_number: number;
  valid: boolean;
  errors: string[];
  trade_at: string | null;
  isin: string | null;
  titolo: string | null;
  side: string | null;
  quantity: number | null;
  price: number | null;
  fees: number | null;
  taxes: number | null;
  trade_currency: string | null;
  notes: string | null;
  asset_id: number | null;
  asset_name: string | null;
  // Ids of existing portfolio transactions this row repeats: skipped on commit unless included.
  duplicate_of?: number[];
}

export type CsvDateFormat = 'DD/MM/YYYY' | 'MM/DD/YYYY' | 'YYYY-MM-DD' | 'DD-MM-YYYY' | 'DD.MM.YYYY' | 'YYYY/MM/DD';

// File column (by name) feeding each transaction field, for files without a dedicated parser.
export interface CsvColumnMapping {
  trade_at: string;
  isin: string;
  side: string;
  quantity: string;
  price: string;
  trade_currency: string | null;
  fees: string | null;
  name: string | null;
  date_format: CsvDateFormat;
}

export interface CsvImportMappingInfo {
  source: 'ai' | 'user';
  mapping: CsvColumnMapping;
  columns: string[];
}

export interface CsvImportPreviewResponse {
  batch_id: number;
  filename: string | null;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  rows: CsvImportPreviewRow[];
  column_mapping: CsvImportMappingInfo | null;
  // Valid rows already present in the portfolio (excluded by default).
  duplicate_rows?: number;
  // Non-blocking notices, e.g. the same file was already imported.
  warnings?: string[];
}

export interface CsvImportCommitRequest {
  include_duplicates?: boolean;
  include_row_numbers?: number[];
}

export interface CsvImportCommitResponse {
  batch_id: number;
  committed_transactions: number;
  skipped_duplicates?: number;
  skipped_duplicate_rows?: number[];
  skipped_invalid?: number;
  errors: string[];
}

// PAC

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

// Benchmarks

export interface BenchmarkItem {
  asset_id: number;
  symbol: string;
  name: string;
}

export interface AssetPricePoint {
  date: string;
  close: number;
}

// Advanced Performance Analytics

export interface MonthlyReturnCell {
  year: number;
  month: number;
  return_pct: number;
}

export interface YearlyReturnItem {
  year: number;
  return_pct: number;
}

export interface MonthlyReturnsResponse {
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  cells: MonthlyReturnCell[];
  yearly_returns: YearlyReturnItem[];
  start_date: string;
  end_date: string;
}

export interface YearlyPerformanceRow {
  year: number;
  twr_pct: number | null;
  mwr_pct: number | null;
  mwr_annualized_pct: number | null;
  converged: boolean;
  is_partial: boolean;
  has_prices: boolean;
  start_date: string;
  end_date: string;
  period_days: number;
}

export interface YearlyPerformanceResponse {
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  rows: YearlyPerformanceRow[];
  start_date: string;
  end_date: string;
  cashflow_basis: 'investor' | 'trades';
}

export interface DrawdownPoint {
  date: string;
  drawdown_pct: number;
}

export interface DrawdownResponse {
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  points: DrawdownPoint[];
  max_drawdown_pct: number;
  max_drawdown_start: string | null;
  max_drawdown_end: string | null;
  current_drawdown_pct: number;
  peak_date: string | null;
  peak_value: number | null;
}

export interface RollingWindowPoint {
  date: string;
  cagr_pct: number | null;
  volatility_pct: number | null;
  sharpe_ratio: number | null;
}

export interface RollingWindowsResponse {
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  window_months: number;
  risk_free_rate_pct: number;
  points: RollingWindowPoint[];
}

export interface RankedPeriod {
  year: number;
  month: number | null;
  return_pct: number;
  label: string;
}

export interface HallOfFameResponse {
  /** 0 for an aggregate view (see portfolio_ids). */
  portfolio_id: number;
  /** Ids of an aggregate view; null/absent for a single portfolio. */
  portfolio_ids?: number[] | null;
  best_months: RankedPeriod[];
  worst_months: RankedPeriod[];
  best_years: RankedPeriod[];
  worst_years: RankedPeriod[];
}

// Copilot

export interface CopilotStatus {
  available: boolean;
  provider: string | null;
  model: string | null;
  source: 'user' | 'server' | null;
}

// ---------------------------------------------------------------------------
// Portfolio Doctor 2.0 — policy, evaluation, Scenario Lab
// (binding contract: docs/doctor2/api-contracts.md §2–§8). Every number here
// is computed by the backend: the frontend only formats it.
// ---------------------------------------------------------------------------

export interface DoctorFeatures {
  policy_enabled: boolean;
  simulator_enabled: boolean;
}

export type DoctorPolicyOperator = 'min' | 'max' | 'range';
export type DoctorPolicySeverity = 'low' | 'medium' | 'high';
export type DoctorRuleStatus = 'PASS' | 'FAIL' | 'UNKNOWN' | 'NOT_APPLICABLE' | 'INACTIVE';
export type DoctorMetricQuality = 'ok' | 'partial' | 'stale' | 'missing';
export type DoctorScopeType = 'single' | 'aggregate';

export interface DoctorMetricDefinition {
  code: string;
  label: string;
  unit: 'pct' | string;
  operators: DoctorPolicyOperator[];
  denominator?: string | null;
  description?: string | null;
  source?: string | null;
  default_warning_margin?: number | null;
  methodology_version?: string | null;
}

export interface DoctorPolicyRule {
  rule_id: string;
  metric_code: string;
  operator: DoctorPolicyOperator;
  min_value: number | null;
  max_value: number | null;
  unit: 'pct' | string;
  precision: number;
  severity: DoctorPolicySeverity;
  warning_margin: number;
  /** null in a draft = backend default (80). */
  min_coverage_pct: number | null;
  /** null in a draft = backend default (5). */
  max_data_age_days: number | null;
  enabled: boolean;
  label?: string | null;
}

export interface DoctorPolicyDocument {
  schema_version: 1;
  rules: DoctorPolicyRule[];
}

export interface DoctorPolicyTemplate {
  /** Contract deviation: templates are identified by `template_id` (`code` accepted as fallback). */
  template_id?: string;
  code?: string;
  name: string;
  description?: string | null;
  template_version?: string | number | null;
  illustrative?: boolean;
  disclaimer?: string | null;
  document: DoctorPolicyDocument;
}

export interface DoctorFieldError {
  field: string;
  code: string;
  message: string;
}

export interface DoctorPolicyScope {
  portfolio_ids: number[];
  scope_type: DoctorScopeType;
  fingerprint: string;
}

export interface DoctorPolicyRead {
  id: number;
  name: string;
  scope: DoctorPolicyScope;
  active: boolean;
  current_version: number;
  document: DoctorPolicyDocument;
  updated_at: string;
  created_at: string;
}

export interface DoctorEvidenceContributor {
  symbol: string | null;
  name: string | null;
  isin: string | null;
  weight_pct: number | null;
}

export interface DoctorRuleEvidence {
  source: string | null;
  denominator: string | null;
  denominator_value: number | null;
  contributors: DoctorEvidenceContributor[];
  notes: string[];
  quote_as_of: string | null;
  calculated_at: string | null;
  methodology_version: string | null;
}

export interface DoctorRuleResult {
  rule_id: string;
  metric_code: string;
  label: string | null;
  operator: DoctorPolicyOperator;
  min_value: number | null;
  max_value: number | null;
  unit: string;
  precision: number;
  severity: DoctorPolicySeverity;
  status: DoctorRuleStatus;
  near_limit: boolean;
  actual: number | null;
  actual_lower: number | null;
  actual_upper: number | null;
  breach_amount: number | null;
  reason: string;
  coverage_pct: number | null;
  quality: DoctorMetricQuality;
  evidence: DoctorRuleEvidence;
}

export interface DoctorDataQuality {
  status: 'ok' | 'stale' | 'partial' | 'unknown';
  last_successful_price_sync: string | null;
  last_sync_status: string | null;
  stale_symbols: string[];
  missing_price_symbols: string[];
  oldest_price_at: string | null;
  note: string | null;
}

export interface DoctorEvaluationSummary {
  passed: number;
  failed: number;
  unknown: number;
  not_applicable: number;
  inactive: number;
  near_limit: number;
  total: number;
}

export interface DoctorPolicyEvaluation {
  status: 'ready' | 'no_policy' | 'empty_portfolio';
  scope: DoctorPolicyScope;
  policy_id: number | null;
  policy_version: number | null;
  policy_name: string | null;
  snapshot_id: string;
  snapshot_as_of: string | null;
  calculated_at: string;
  methodology_version: string;
  data_quality: DoctorDataQuality;
  summary: DoctorEvaluationSummary;
  results: DoctorRuleResult[];
}

export interface DoctorPolicyValidateResponse {
  valid: boolean;
  field_errors: DoctorFieldError[];
  normalized_document: DoctorPolicyDocument | null;
}

export interface DoctorPolicyDiffEntry {
  rule_id: string;
  metric_code: string;
  change: 'added' | 'removed' | 'modified';
  before: Partial<DoctorPolicyRule> | null;
  after: Partial<DoctorPolicyRule> | null;
}

export interface DoctorPolicyPreviewResponse {
  valid: boolean;
  field_errors: DoctorFieldError[];
  normalized_document: DoctorPolicyDocument | null;
  diff: DoctorPolicyDiffEntry[];
  evaluation_before: DoctorPolicyEvaluation | null;
  evaluation_after: DoctorPolicyEvaluation | null;
  confirmation_token: string | null;
  expires_at: string | null;
  base_version: number | null;
  document_hash: string | null;
}

export type DoctorPolicySource = 'manual' | 'copilot' | 'template';

export interface DoctorPolicyVersion {
  version_number: number;
  source: string;
  confirmed_at: string;
  actor?: string | null;
  diff: DoctorPolicyDiffEntry[];
  document?: DoctorPolicyDocument | null;
  document_hash?: string | null;
}

/** SSE `policy_draft` payload of the Copilot (contract §7). */
export interface DoctorPolicyDraftPayload {
  portfolio_ids: number[];
  preview: DoctorPolicyPreviewResponse;
  name?: string | null;
}

// ---- Scenario Lab (§8) ----

export type DoctorScenarioMode = 'manual' | 'new_cash_only' | 'rebalance';

export interface DoctorScenarioOperation {
  symbol?: string;
  asset_id?: number;
  action: 'buy' | 'sell';
  amount: number;
}

export interface DoctorScenarioConstraints {
  no_sell: boolean;
  max_turnover_pct: number | null;
  keep_equity_total: boolean;
  use_cash_balance?: boolean;
}

export interface DoctorScenarioInput {
  mode: DoctorScenarioMode;
  new_cash: number;
  operations: DoctorScenarioOperation[];
  target_weights: Record<string, number>;
  constraints: DoctorScenarioConstraints;
  fee_model: { pct: number; fixed: number };
  tax_model: 'none';
  label: string;
}

export interface DoctorScenarioRequest extends DoctorScenarioInput {
  portfolio_ids: number[];
  snapshot_id: string | null;
  policy_version: number | null;
}

export interface DoctorScenarioCompareRequest {
  portfolio_ids: number[];
  snapshot_id: string | null;
  policy_version: number | null;
  scenarios: DoctorScenarioInput[];
}

export interface DoctorMetricValue {
  code: string;
  value: number | null;
  lower: number | null;
  upper: number | null;
  unit: string;
  coverage_pct: number | null;
  quality: DoctorMetricQuality;
  source?: string | null;
  denominator?: string | null;
  denominator_value?: number | null;
  contributors?: DoctorEvidenceContributor[];
  notes?: string[];
}

/** Post-scenario volatility is never estimated by the MVP: always `not_available` with a reason. */
export interface DoctorScenarioVolatility {
  value: number | null;
  status: 'not_available' | string;
  reason: string | null;
}

export interface DoctorScenarioSide {
  invested_value: number | null;
  cash_value: number | null;
  total_value: number | null;
  metrics: Record<string, DoctorMetricValue> | DoctorMetricValue[];
  evaluation_status: 'ready' | 'no_policy' | 'empty_portfolio';
  evaluation_summary: DoctorEvaluationSummary | null;
  rule_results: DoctorRuleResult[];
  volatility: DoctorScenarioVolatility | null;
}

export interface DoctorScenarioChange {
  asset_id: number | null;
  symbol: string | null;
  name?: string | null;
  isin?: string | null;
  asset_class?: string | null;
  action?: 'buy' | 'sell' | 'hold';
  before_value: number | null;
  after_value: number | null;
  delta_value: number | null;
  before_weight: number | null;
  after_weight: number | null;
  delta_weight?: number | null;
  fees?: number | null;
}

/** A rule touched by the scenario (§8.1 `RuleChange`); a bare rule id is still tolerated. */
export type DoctorScenarioViolationRef =
  | string
  | {
    rule_id?: string | null;
    metric_code?: string | null;
    label?: string | null;
    reason?: string | null;
    before_status?: string | null;
    after_status?: string | null;
    before_actual?: number | null;
    after_actual?: number | null;
  };

/** Hypothetical costs of a scenario: an object, never a bare number. */
export interface DoctorScenarioCosts {
  total: number | null;
  variable: number | null;
  fixed: number | null;
  operations: number | null;
  fee_model: { pct: number; fixed: number } | null;
}

export type DoctorScenarioInfeasibleCode =
  | 'insufficient_cash'
  | 'no_sell'
  | 'impossible_without_sell'
  | 'oversell'
  | 'capacity_exceeded'
  | 'keep_equity_total'
  | 'turnover_exceeded'
  | 'empty_portfolio';

export interface DoctorScenarioResult {
  label?: string | null;
  mode: DoctorScenarioMode;
  feasible: boolean;
  infeasible_code: DoctorScenarioInfeasibleCode | string | null;
  infeasible_reason: string | null;
  scope: DoctorPolicyScope;
  policy_id: number | null;
  policy_version: number | null;
  before: DoctorScenarioSide;
  after: DoctorScenarioSide | null;
  changes: DoctorScenarioChange[];
  warnings: string[];
  violations_resolved: DoctorScenarioViolationRef[];
  violations_new: DoctorScenarioViolationRef[];
  required_new_cash: number | null;
  total_before: number | null;
  total_after: number | null;
  cash_in: number | null;
  costs: DoctorScenarioCosts | null;
  turnover_pct: number | null;
  methodology_version: string;
  snapshot_id: string;
  data_quality: DoctorDataQuality | null;
  calculated_at: string;
  tax_model: 'none';
  disclaimer: string;
}

/** One row of the comparison ranking: `costs` is the total cost (a number) here. */
export interface DoctorScenarioRankItem {
  index: number;
  label: string | null;
  rank: number;
  feasible: boolean;
  failed_after: number | null;
  unknown_after: number | null;
  violations_resolved: number;
  violations_new: number;
  costs: number | null;
  cash_in: number | null;
  turnover_pct: number | null;
}

export interface DoctorScenarioCompareResponse {
  scope?: DoctorPolicyScope;
  policy_id?: number | null;
  policy_version?: number | null;
  calculated_at?: string;
  data_quality?: DoctorDataQuality | null;
  current?: DoctorScenarioSide | null;
  scenarios: DoctorScenarioResult[];
  ranking?: DoctorScenarioRankItem[];
  best_index?: number | null;
  explanation?: string | null;
  snapshot_id?: string | null;
  methodology_version?: string | null;
  disclaimer?: string | null;
}
