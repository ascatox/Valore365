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
  max_position_weight: number;
  overlap_score: number;
  portfolio_volatility: number | null;
  weighted_ter: number | null;
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

export interface InstantAnalyzeResponse {
  summary: PortfolioAnalyzeSummary;
  positions: ResolvedPublicPosition[];
  unresolved: InstantAnalyzeUnresolvedItem[];
  parse_errors: InstantAnalyzeLineError[];
  metrics: PortfolioAnalyzeMetrics;
  category_scores: PortfolioHealthCategoryScores;
  alerts: PortfolioAnalyzeAlert[];
  suggestions: PortfolioAnalyzeSuggestion[];
  cta: InstantAnalyzeCta;
}

export interface UserSettings {
  user_id: string;
  broker_default_fee: number;
  copilot_provider: string;
  copilot_model: string;
  copilot_api_key_set: boolean;
  fire_annual_expenses: number;
  fire_annual_contribution: number;
  fire_safe_withdrawal_rate: number;
  fire_current_age: number | null;
  fire_target_age: number | null;
}

export interface UserSettingsUpdateInput {
  broker_default_fee?: number;
  copilot_provider?: string;
  copilot_model?: string;
  copilot_api_key?: string;
  fire_annual_expenses?: number;
  fire_annual_contribution?: number;
  fire_safe_withdrawal_rate?: number;
  fire_current_age?: number | null;
  fire_target_age?: number | null;
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
}

export interface PortfolioHealthSuggestion {
  priority: 'low' | 'medium' | 'high';
  message: string;
}

export interface PortfolioHealthResponse {
  portfolio_id: number;
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
  portfolio_id: number;
  num_simulations: number;
  horizons: number[];
  projections: MonteCarloYearProjection[];
  annualized_mean_return_pct: number;
  annualized_volatility_pct: number;
}

export interface DecumulationYearProjection {
  year: number;
  age: number | null;
  gross_withdrawal: number;
  net_withdrawal: number;
  p25_ending_capital: number;
  p50_ending_capital: number;
  p75_ending_capital: number;
  p50_effective_withdrawal_rate_pct: number;
  depletion_probability_pct: number;
}

export interface DecumulationPlanResponse {
  portfolio_id: number;
  initial_capital: number;
  annual_withdrawal: number;
  annual_other_income: number;
  inflation_rate_pct: number;
  horizon_years: number;
  num_simulations: number;
  annualized_mean_return_pct: number;
  annualized_volatility_pct: number;
  sustainable_withdrawal: number;
  success_rate_pct: number;
  depletion_probability_pct: number;
  p25_terminal_value: number;
  p50_terminal_value: number;
  p75_terminal_value: number;
  depletion_year_p50: number | null;
  projections: DecumulationYearProjection[];
}

export interface AggregateDecumulationPlanResponse {
  portfolio_ids: number[];
  base_currency: string;
  initial_capital: number;
  annual_withdrawal: number;
  annual_other_income: number;
  inflation_rate_pct: number;
  horizon_years: number;
  num_simulations: number;
  annualized_mean_return_pct: number;
  annualized_volatility_pct: number;
  sustainable_withdrawal: number;
  success_rate_pct: number;
  depletion_probability_pct: number;
  p25_terminal_value: number;
  p50_terminal_value: number;
  p75_terminal_value: number;
  depletion_year_p50: number | null;
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

export interface TWRResult {
  twr_pct: number;
  twr_annualized_pct: number | null;
  period_days: number;
  start_date: string;
  end_date: string;
}

export interface MWRResult {
  mwr_pct: number | null;
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
  current_value: number;
  absolute_gain: number;
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

export interface Position {
  asset_id: number;
  symbol: string;
  name: string;
  asset_type: string;
  quantity: number;
  avg_cost: number;
  market_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
  day_change_pct: number;
  weight: number;
  first_trade_at?: string | null;
  price_stale?: boolean;
  price_date?: string | null;
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
  dividend_yield: number | null;
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
  portfolio_weight_pct: number;
  holdings_available: boolean;
  holdings_source: 'justetf' | 'yfinance' | 'missing';
  failure_reason: string | null;
  top_holdings: XRayHolding[];
}

export interface XRayCoverageIssue {
  asset_id: number;
  symbol: string;
  name: string;
  reason: string;
}

export interface XRayResponse {
  portfolio_id: number;
  aggregated_holdings: XRayHolding[];
  etf_details: XRayEtfDetail[];
  etf_count: number;
  coverage_pct: number;
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
}

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
}

export interface StressTestResponse {
  portfolio_id: number;
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
}

export interface MarketNewsResponse {
  items: MarketNewsItem[];
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

// Copilot

export interface CopilotStatus {
  available: boolean;
  provider: string | null;
  model: string | null;
  source: 'user' | 'server' | null;
}
