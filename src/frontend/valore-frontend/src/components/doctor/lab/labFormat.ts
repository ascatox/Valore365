import type {
  DoctorMetricValue,
  DoctorScenarioInput,
  DoctorScenarioResult,
  DoctorScenarioSide,
  DoctorScenarioViolationRef,
} from '../../../services/api/types';
import { formatPctValue, NOT_AVAILABLE, PRIVACY_MASK } from '../policy/policyFormat';

export const MAX_SCENARIOS = 3;

/**
 * `required_new_cash` in whole units of the currency, rounded UP (a minimum is
 * never shown lower than it is): 227.028,58 → «227.029 €», the same figure the
 * backend writes in `infeasible_reason` (golden PRD example). Display only.
 */
export function formatRequiredCash(value: number | null | undefined, currency = 'EUR', privacy = false): string {
  if (privacy) return PRIVACY_MASK;
  if (value == null || !Number.isFinite(value)) return NOT_AVAILABLE;
  const whole = Math.ceil(value - 1e-9);
  try {
    return new Intl.NumberFormat('it-IT', { style: 'currency', currency, maximumFractionDigits: 0, minimumFractionDigits: 0 }).format(whole);
  } catch {
    return `${new Intl.NumberFormat('it-IT', { maximumFractionDigits: 0 }).format(whole)} ${currency}`;
  }
}

export function emptyScenario(label: string, overrides: Partial<DoctorScenarioInput> = {}): DoctorScenarioInput {
  return {
    mode: 'new_cash_only',
    new_cash: 0,
    operations: [],
    target_weights: {},
    constraints: { no_sell: true, max_turnover_pct: null, keep_equity_total: false, use_cash_balance: false },
    fee_model: { pct: 0, fixed: 0 },
    tax_model: 'none',
    label,
    ...overrides,
  };
}

export function sideMetric(side: DoctorScenarioSide | null | undefined, code: string): DoctorMetricValue | null {
  if (!side?.metrics) return null;
  if (Array.isArray(side.metrics)) return side.metrics.find((metric) => metric.code === code) ?? null;
  return side.metrics[code] ?? null;
}

export function sideMetricCodes(side: DoctorScenarioSide | null | undefined): string[] {
  if (!side?.metrics) return [];
  return Array.isArray(side.metrics) ? side.metrics.map((metric) => metric.code) : Object.keys(side.metrics);
}

/** Metric value as the backend gave it: point value, bounds, or N/D. */
export function formatMetric(metric: DoctorMetricValue | null | undefined, precision = 1): string {
  if (!metric) return NOT_AVAILABLE;
  if (metric.value != null && Number.isFinite(metric.value)) return formatPctValue(metric.value, metric.code === 'weighted_ter_pct' ? 2 : precision);
  if (metric.lower != null && metric.upper != null) return `tra ${formatPctValue(metric.lower, precision)} e ${formatPctValue(metric.upper, precision)}`;
  return NOT_AVAILABLE;
}

export function isIncomplete(metric: DoctorMetricValue | null | undefined): boolean {
  return !metric || metric.value == null || metric.quality === 'partial' || metric.quality === 'missing' || metric.quality === 'stale';
}

export function violationKey(ref: DoctorScenarioViolationRef): { ruleId: string | null; metricCode: string | null; label: string | null; reason: string | null } {
  if (typeof ref === 'string') return { ruleId: ref, metricCode: null, label: null, reason: null };
  return { ruleId: ref.rule_id ?? null, metricCode: ref.metric_code ?? null, label: ref.label ?? null, reason: ref.reason ?? null };
}

/** Metric codes whose rule the scenario resolves / newly breaks (by metric code or via rule id). */
export function touchedMetrics(result: DoctorScenarioResult, ruleMetric: Map<string, string>) {
  const toCodes = (refs: DoctorScenarioViolationRef[] | undefined) => new Set((refs ?? []).map((ref) => {
    const key = violationKey(ref);
    return key.metricCode ?? (key.ruleId ? ruleMetric.get(key.ruleId) ?? key.ruleId : null);
  }).filter((code): code is string => code != null));
  return { resolved: toCodes(result.violations_resolved), created: toCodes(result.violations_new) };
}
