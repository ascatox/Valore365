// Auditor dei calcoli — client API (docs/auditor/architecture.md §6.1, §7.3).
// Utente: esiti dei controlli notturni dei propri portafogli (TASK-81).
// Amministratore: ultima corsa notturna (TASK-80).
import { apiFetch } from './client';
import { doctorScopeQuery } from './doctor';

export type AuditorCheckStatus = 'passed' | 'in_review';

export interface AuditorCheck {
  title: string;
  status: AuditorCheckStatus;
}

export interface AuditorArea {
  area: string;
  label: string;
  status: AuditorCheckStatus;
  checks: AuditorCheck[];
}

/** GET /doctor/auditor/summary: nessun id di regola, nessuna evidenza. */
export interface AuditorSummary {
  available: boolean;
  run_finished_at: string | null;
  checks_passed: number;
  checks_in_review: number;
  areas: AuditorArea[];
}

export type AuditorRunStatus = 'running' | 'success' | 'completed_with_failures' | 'failed' | 'interrupted';
export type AuditorSeverity = 'P0' | 'P1' | 'P2';

export interface AuditorRunSummary {
  run_id: string;
  status: AuditorRunStatus;
  trigger: string;
  app_version: string;
  started_at: string | null;
  finished_at: string | null;
  portfolios_total: number;
  rules_total: number;
  users_total?: number;
  users_failed?: number;
  deadline_exceeded?: boolean;
  error_type?: string | null;
  counts: { pass: number; fail: number; skip: number; error: number };
  failing_rules: { rule_id: string; severity: AuditorSeverity; portfolios: number }[];
}

export interface AuditorFailingRule {
  rule_id: string;
  title: string;
  area: string | null;
  severity: AuditorSeverity;
  portfolios_failing: number;
  since: string;
}

/** GET /admin/auditor/latest (require_admin): solo conteggi e id di regole. */
export interface AuditorAdminLatest {
  run: AuditorRunSummary | null;
  failing: AuditorFailingRule[];
  errors: { rule_id: string; portfolios: number }[];
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isStatus = (value: unknown): value is AuditorCheckStatus => value === 'passed' || value === 'in_review';

const UNAVAILABLE: AuditorSummary = { available: false, run_finished_at: null, checks_passed: 0, checks_in_review: 0, areas: [] };

/** Forma minima del payload; qualunque cosa d'altro diventa «non disponibile» (nessun indicatore). */
export function normalizeAuditorSummary(value: unknown): AuditorSummary {
  if (!isObject(value) || value.available !== true || typeof value.run_finished_at !== 'string') return UNAVAILABLE;
  const areas: AuditorArea[] = [];
  for (const raw of Array.isArray(value.areas) ? value.areas : []) {
    if (!isObject(raw) || typeof raw.label !== 'string' || !Array.isArray(raw.checks)) continue;
    const checks = raw.checks.filter(
      (check): check is AuditorCheck => isObject(check) && typeof check.title === 'string' && isStatus(check.status),
    );
    if (!checks.length) continue;
    areas.push({
      area: typeof raw.area === 'string' ? raw.area : raw.label,
      label: raw.label,
      status: checks.some((check) => check.status === 'in_review') ? 'in_review' : 'passed',
      checks,
    });
  }
  const all = areas.flatMap((area) => area.checks);
  if (!all.length) return UNAVAILABLE;
  return {
    available: true,
    run_finished_at: value.run_finished_at,
    checks_passed: all.filter((check) => check.status === 'passed').length,
    checks_in_review: all.filter((check) => check.status === 'in_review').length,
    areas,
  };
}

/** GET /doctor/auditor/summary?<doctorScopeQuery> (portafoglio singolo o vista aggregata). */
export async function getAuditorSummary(portfolioIds: number[]): Promise<AuditorSummary> {
  return normalizeAuditorSummary(await apiFetch<unknown>(`/doctor/auditor/summary?${doctorScopeQuery(portfolioIds)}`));
}

/** GET /admin/auditor/latest. */
export const getAuditorAdminLatest = (): Promise<AuditorAdminLatest> =>
  apiFetch<AuditorAdminLatest>('/admin/auditor/latest');

/** Etichette delle aree (stesse di `AREAS` in services/auditor/registry.py), per la vista Admin. */
export const AUDITOR_AREA_LABELS: Record<string, string> = {
  stress: 'Stress test',
  classification: 'Classificazione degli strumenti',
  rebalance: 'Ribilanciamento e PAC',
  simulation: 'Simulazioni',
  costs: 'Costi',
  income: 'Reddito e dividendi',
  montecarlo: 'Proiezioni Monte Carlo',
  daily: 'Variazioni giornaliere',
  values: 'Valori, pesi e liquidità',
  aggregate: 'Vista aggregata',
  performance: 'Rendimenti',
  doctor: 'Metriche del Doctor',
  data: 'Qualità dei dati importati',
};
