import type {
  DoctorMetricDefinition,
  DoctorPolicyEvaluation,
  DoctorPolicyPreviewResponse,
  DoctorPolicyRead,
  DoctorRuleResult,
} from '../../../services/api/types';

// Contract-shaped fixtures (docs/doctor2/api-contracts.md §4–§5) for the Doctor 2.0 tests.

export const METRICS: DoctorMetricDefinition[] = [
  {
    code: 'max_single_position_pct',
    label: 'Peso massimo singola posizione',
    unit: 'pct',
    operators: ['max'],
    denominator: 'Valore investito escluso cash',
    description: 'Peso della security canonica più grande sul valore investito (ISIN, aggregata fra listing).',
  },
  { code: 'usa_exposure_pct', label: 'Esposizione USA (look-through)', unit: 'pct', operators: ['min', 'max', 'range'], denominator: 'Valore investito escluso cash', description: 'Look-through X-Ray.' },
  { code: 'equity_weight_pct', label: 'Quota azionaria', unit: 'pct', operators: ['min', 'max', 'range'], denominator: 'Valore investito escluso cash', description: 'Classificatore comune.' },
];

export function ruleResult(overrides: Partial<DoctorRuleResult> = {}): DoctorRuleResult {
  return {
    rule_id: 'max-single',
    metric_code: 'max_single_position_pct',
    label: 'Max singolo ETF',
    operator: 'max',
    min_value: null,
    max_value: 35,
    unit: 'pct',
    precision: 1,
    severity: 'high',
    status: 'FAIL',
    near_limit: false,
    actual: 46.6,
    actual_lower: null,
    actual_upper: null,
    breach_amount: 11.6,
    reason: 'VWRA 46,6%: supera il tuo limite 35% di 11,6 punti percentuali',
    coverage_pct: 100,
    quality: 'ok',
    evidence: {
      source: 'asset_classification',
      denominator: 'Valore investito escluso cash',
      denominator_value: 125000,
      contributors: [{ symbol: 'VWRA', name: 'Vanguard FTSE All-World', isin: 'IE00BK5BQT80', weight_pct: 46.6 }],
      notes: ['Security canonica per ISIN'],
      quote_as_of: '2026-11-03T17:30:00Z',
      calculated_at: '2026-11-04T08:00:00Z',
      methodology_version: 'doctor-policy-1.0',
    },
    ...overrides,
  };
}

export const RESULTS: DoctorRuleResult[] = [
  ruleResult(),
  ruleResult({
    rule_id: 'usa-max', metric_code: 'usa_exposure_pct', label: null, status: 'UNKNOWN', actual: null, actual_lower: 52, actual_upper: 71,
    max_value: 60, breach_amount: null, coverage_pct: 62, quality: 'partial', severity: 'medium',
    reason: 'Non possiamo verificare il limite USA: copertura insufficiente',
  }),
  ruleResult({
    rule_id: 'equity-range', metric_code: 'equity_weight_pct', label: null, status: 'PASS', near_limit: true, operator: 'range',
    min_value: 60, max_value: 80, actual: 79, breach_amount: null, severity: 'medium', reason: 'Quota azionaria 79,0%: vicina al limite massimo 80%',
  }),
  ruleResult({
    rule_id: 'top3', metric_code: 'top3_positions_pct', label: null, status: 'PASS', actual: 40, max_value: 70, breach_amount: null, severity: 'low', reason: 'Prime tre posizioni 40,0%: entro il limite',
  }),
  ruleResult({
    rule_id: 'ter', metric_code: 'weighted_ter_pct', label: null, status: 'UNKNOWN', actual: 0.2, max_value: 0.3, breach_amount: null, quality: 'stale',
    precision: 2, reason: 'Quote più vecchie di 5 giorni: verifica sospesa',
  }),
];

export function evaluation(overrides: Partial<DoctorPolicyEvaluation> = {}): DoctorPolicyEvaluation {
  return {
    status: 'ready',
    scope: { portfolio_ids: [1], scope_type: 'single', fingerprint: 'p:1' },
    policy_id: 7,
    policy_version: 3,
    policy_name: 'I miei parametri',
    snapshot_id: 'abc123',
    snapshot_as_of: '2026-11-03T17:30:00Z',
    calculated_at: '2026-11-04T08:00:00Z',
    methodology_version: 'doctor-policy-1.0',
    data_quality: {
      status: 'ok', last_successful_price_sync: '2026-11-04T07:00:00Z', last_sync_status: 'ok',
      stale_symbols: [], missing_price_symbols: [], oldest_price_at: '2026-11-03T17:30:00Z', note: null,
    },
    summary: { passed: 2, failed: 1, unknown: 2, not_applicable: 0, inactive: 0, near_limit: 1, total: 5 },
    results: RESULTS,
    ...overrides,
  };
}

export function policyRead(overrides: Partial<DoctorPolicyRead> = {}): DoctorPolicyRead {
  return {
    id: 7,
    name: 'I miei parametri',
    scope: { portfolio_ids: [1], scope_type: 'single', fingerprint: 'p:1' },
    active: true,
    current_version: 3,
    document: {
      schema_version: 1,
      rules: [{
        rule_id: 'max-single', metric_code: 'max_single_position_pct', operator: 'max', min_value: null, max_value: 35, unit: 'pct',
        precision: 1, severity: 'high', warning_margin: 2, min_coverage_pct: 80, max_data_age_days: 5, enabled: true, label: 'Max singolo ETF',
      }],
    },
    updated_at: '2026-11-01T10:00:00Z',
    created_at: '2026-10-01T10:00:00Z',
    ...overrides,
  };
}

export function preview(overrides: Partial<DoctorPolicyPreviewResponse> = {}): DoctorPolicyPreviewResponse {
  const after = policyRead().document;
  after.rules[0].max_value = 50;
  return {
    valid: true,
    field_errors: [],
    normalized_document: after,
    diff: [{
      rule_id: 'max-single', metric_code: 'max_single_position_pct', change: 'modified',
      before: { operator: 'max', max_value: 35, precision: 1, label: 'Max singolo ETF' },
      after: { operator: 'max', max_value: 50, precision: 1, label: 'Max singolo ETF' },
    }],
    evaluation_before: evaluation(),
    evaluation_after: evaluation({ summary: { passed: 3, failed: 0, unknown: 2, not_applicable: 0, inactive: 0, near_limit: 1, total: 5 } }),
    confirmation_token: 'tok-123',
    expires_at: '2026-11-04T08:15:00Z',
    base_version: 3,
    document_hash: 'hash',
    ...overrides,
  };
}

export const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

export const errorResponse = (status: number, code: string, message: string, details: Record<string, unknown> | null = null) =>
  jsonResponse({ error: { code, message, details } }, status);
