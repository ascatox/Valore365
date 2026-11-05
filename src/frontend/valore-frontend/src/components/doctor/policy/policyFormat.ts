import { STORAGE_KEYS } from '../../dashboard/constants';
import { ApiRequestError } from '../../../services/api/client';
import type {
  DoctorDataQuality,
  DoctorEvaluationSummary,
  DoctorMetricDefinition,
  DoctorPolicyEvaluation,
  DoctorPolicyOperator,
  DoctorPolicyRule,
  DoctorPolicySeverity,
  DoctorRuleResult,
  DoctorRuleStatus,
} from '../../../services/api/types';

// Formatting only: every number shown here comes from the backend as is
// (no financial calculation happens in the browser).

export const PRIVACY_MASK = '******';
export const NOT_AVAILABLE = 'N/D';

export function isDoctorPrivacyMode(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled) === 'true';
  } catch {
    return false;
  }
}

/** Fallback labels of the MVP metric registry (contract §2), used until /doctor/metrics answers. */
export const METRIC_LABELS: Record<string, string> = {
  equity_weight_pct: 'Quota azionaria',
  bond_weight_pct: 'Quota obbligazionaria',
  gold_weight_pct: 'Quota oro / metalli preziosi',
  max_single_position_pct: 'Peso massimo singola posizione',
  top3_positions_pct: 'Peso prime tre posizioni',
  usa_exposure_pct: 'Esposizione USA (look-through)',
  weighted_ter_pct: 'TER medio ponderato',
  etf_overlap_pct: 'Overlap ETF',
};

export function metricLabel(code: string, metrics?: DoctorMetricDefinition[] | null): string {
  return metrics?.find((metric) => metric.code === code)?.label ?? METRIC_LABELS[code] ?? code;
}

export function ruleName(rule: Pick<DoctorRuleResult, 'label' | 'metric_code'>, metrics?: DoctorMetricDefinition[] | null): string {
  return rule.label?.trim() || metricLabel(rule.metric_code, metrics);
}

function numberFormat(precision: number): Intl.NumberFormat {
  const digits = Math.max(0, Math.min(3, Number.isFinite(precision) ? precision : 1));
  return new Intl.NumberFormat('it-IT', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** `46,6%`; `N/D` when the backend has no value. */
export function formatPctValue(value: number | null | undefined, precision = 1): string {
  if (value == null || !Number.isFinite(value)) return NOT_AVAILABLE;
  return `${numberFormat(precision).format(value)}%`;
}

/** `11,6 pp` (percentage points). */
export function formatPp(value: number | null | undefined, precision = 1): string {
  if (value == null || !Number.isFinite(value)) return NOT_AVAILABLE;
  return `${numberFormat(precision).format(value)} pp`;
}

/** Absolute amounts are always masked in Privacy Mode. */
export function formatMoney(value: number | null | undefined, currency = 'EUR', privacy = false): string {
  if (privacy) return PRIVACY_MASK;
  if (value == null || !Number.isFinite(value)) return NOT_AVAILABLE;
  try {
    return new Intl.NumberFormat('it-IT', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value);
  } catch {
    return `${numberFormat(2).format(value)} ${currency}`;
  }
}

// A money amount inside free text: «227.029 €», «€ 10.000», «1.500,50 EUR», «EUR 41000», «10 euro».
// Percentages («46,6%») and plain numbers are never matched.
const SPACE = '[\\s\\u00A0\\u202F]?';
const NUMBER = '[-+\\u2212]?\\d(?:[\\d.,\\u00A0\\u202F]*\\d)?';
const MONEY_IN_TEXT = new RegExp(
  `(?:€|\\bEUR)${SPACE}${NUMBER}|${NUMBER}${SPACE}(?:€|EUR\\b|euro\\b)`,
  'gi',
);

/**
 * Masks the money amounts of a backend free-text string (rule reasons, notes,
 * warnings, infeasible reasons, explanations) in Privacy Mode. Percentages stay
 * visible. `privacy` defaults to the stored Privacy Mode flag.
 */
export function maskMoneyInText<T extends string | null | undefined>(text: T, privacy: boolean = isDoctorPrivacyMode()): T {
  if (!privacy || !text) return text;
  return text.replace(MONEY_IN_TEXT, PRIVACY_MASK) as T;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return NOT_AVAILABLE;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return NOT_AVAILABLE;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export const OPERATOR_LABELS: Record<DoctorPolicyOperator, string> = {
  min: 'Minimo',
  max: 'Massimo',
  range: 'Intervallo',
};

export const SEVERITY_LABELS: Record<DoctorPolicySeverity, string> = {
  low: 'Bassa',
  medium: 'Media',
  high: 'Alta',
};

/** `max 35%`, `min 20%`, `20%–40%`. */
export function formatThreshold(rule: Pick<DoctorPolicyRule, 'operator' | 'min_value' | 'max_value' | 'precision'>): string {
  const precision = rule.precision ?? 1;
  if (rule.operator === 'max') return `max ${formatPctValue(rule.max_value, precision)}`;
  if (rule.operator === 'min') return `min ${formatPctValue(rule.min_value, precision)}`;
  return `${formatPctValue(rule.min_value, precision)}–${formatPctValue(rule.max_value, precision)}`;
}

/** Observed value, the conservative bounds when only those are known, else N/D. */
export function formatObserved(rule: Pick<DoctorRuleResult, 'actual' | 'actual_lower' | 'actual_upper' | 'precision'>): string {
  const precision = rule.precision ?? 1;
  if (rule.actual != null && Number.isFinite(rule.actual)) return formatPctValue(rule.actual, precision);
  if (rule.actual_lower != null && rule.actual_upper != null) {
    return `tra ${formatPctValue(rule.actual_lower, precision)} e ${formatPctValue(rule.actual_upper, precision)}`;
  }
  return NOT_AVAILABLE;
}

export type RuleTone = 'fail' | 'unknown' | 'near_limit' | 'pass' | 'not_applicable' | 'inactive';

export interface RuleStatusMeta {
  tone: RuleTone;
  label: string;
  color: string;
}

export function ruleStatusMeta(status: DoctorRuleStatus, nearLimit: boolean): RuleStatusMeta {
  switch (status) {
    case 'FAIL':
      return { tone: 'fail', label: 'Violato', color: 'red' };
    case 'UNKNOWN':
      return { tone: 'unknown', label: 'Non verificabile', color: 'gray' };
    case 'PASS':
      return nearLimit
        ? { tone: 'near_limit', label: 'Vicino al limite', color: 'yellow' }
        : { tone: 'pass', label: 'Rispettato', color: 'teal' };
    case 'NOT_APPLICABLE':
      return { tone: 'not_applicable', label: 'Non applicabile', color: 'gray' };
    case 'INACTIVE':
    default:
      return { tone: 'inactive', label: 'Disattivato', color: 'gray' };
  }
}

export const QUALITY_LABELS: Record<string, string> = {
  ok: 'Dati completi',
  partial: 'Dati parziali',
  stale: 'Dati non aggiornati',
  missing: 'Dati mancanti',
  unknown: 'Qualità dati sconosciuta',
};

const plural = (count: number, singular: string, pluralForm: string) => `${count} ${count === 1 ? singular : pluralForm}`;

/**
 * «4 rispettati · 1 violato · 1 non verificabile». UNKNOWN rules are always
 * spelled out: never «5/6 rispettati».
 */
export function formatComplianceSummary(summary: DoctorEvaluationSummary | null | undefined): string {
  if (!summary) return NOT_AVAILABLE;
  const parts = [
    plural(summary.passed ?? 0, 'rispettato', 'rispettati'),
    plural(summary.failed ?? 0, 'violato', 'violati'),
  ];
  if ((summary.unknown ?? 0) > 0) parts.push(plural(summary.unknown, 'non verificabile', 'non verificabili'));
  if ((summary.not_applicable ?? 0) > 0) parts.push(plural(summary.not_applicable, 'non applicabile', 'non applicabili'));
  if ((summary.inactive ?? 0) > 0) parts.push(plural(summary.inactive, 'disattivato', 'disattivati'));
  return parts.join(' · ');
}

export function formatNearLimit(summary: DoctorEvaluationSummary | null | undefined): string | null {
  const count = summary?.near_limit ?? 0;
  if (count <= 0) return null;
  return count === 1 ? 'di cui 1 vicino al limite' : `di cui ${count} vicini al limite`;
}

export function dataQualityLabel(quality: DoctorDataQuality | null | undefined): { label: string; color: string } {
  switch (quality?.status) {
    case 'ok':
      return { label: 'Quotazioni aggiornate', color: 'teal' };
    case 'stale':
      return { label: 'Quotazioni non aggiornate', color: 'orange' };
    case 'partial':
      return { label: 'Dati parziali', color: 'yellow' };
    default:
      return { label: 'Aggiornamento sconosciuto', color: 'gray' };
  }
}

export const SCENARIO_DISCLAIMER = 'Simulazione teorica; nessun ordine eseguito.';

export const POLICY_VERSION_CONFLICT_MESSAGE = "La policy è stata modificata in un'altra scheda: ricarica";
export const POLICY_CONFIRMATION_INVALID_MESSAGE =
  'La conferma non è più valida (scaduta o già usata): genera di nuovo l\'anteprima e conferma.';

/** Italian message for the Doctor API errors (contract §5). */
export function doctorErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    switch (error.code) {
      case 'version_conflict':
        return POLICY_VERSION_CONFLICT_MESSAGE;
      case 'confirmation_invalid':
        return POLICY_CONFIRMATION_INVALID_MESSAGE;
      case 'snapshot_changed':
        return 'I dati del portafoglio sono cambiati: riesegui la simulazione.';
      case 'feature_disabled':
        return 'Funzione non disponibile al momento.';
      case 'not_found':
        return 'Ambito non trovato: uno dei portafogli potrebbe non esistere più.';
      default:
        return error.message || 'Errore inatteso.';
    }
  }
  if (error instanceof Error) return error.message;
  return 'Errore inatteso.';
}

export function isDoctorErrorCode(error: unknown, code: string): boolean {
  return error instanceof ApiRequestError && error.code === code;
}

export function fieldErrorsFrom(error: unknown) {
  if (!(error instanceof ApiRequestError)) return [];
  const raw = (error.details as { field_errors?: unknown } | null)?.field_errors;
  return Array.isArray(raw) ? (raw as Array<{ field: string; code: string; message: string }>) : [];
}

/** Is the value a well-formed evaluation (guards against empty / legacy bodies). */
export function isEvaluation(value: unknown): value is DoctorPolicyEvaluation {
  return Boolean(value && typeof value === 'object' && typeof (value as { status?: unknown }).status === 'string'
    && Array.isArray((value as { results?: unknown }).results));
}
