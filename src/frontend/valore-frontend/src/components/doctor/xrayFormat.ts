/** X-Ray display helpers (TASK-48: look-through coverage, unclassified share, data date). */

import type { XRayEtfDetail, XRayLookthroughStatus, XRayResponse } from '../../services/api';

export const UNCLASSIFIED_LABEL = 'Non classificato';

/** "2026-09-30" -> "30/09/2026" (no timezone shift). */
export function formatIsoDateIt(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split('-');
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

export function formatPctIt(value: number): string {
  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1).replace('.', ',')}%`;
}

/** Text of the look-through coverage badge (TASK-48). */
export function lookthroughCoverageText(pct: number): string {
  return `Scomposto il ${formatPctIt(pct)} del portafoglio`;
}

type ApplicableCoverageInput = Pick<
  XRayResponse,
  'applicable_lookthrough_coverage_pct' | 'not_applicable_pct' | 'missing_pct'
> & { etf_details: Array<Pick<XRayEtfDetail, 'lookthrough_status' | 'lookthrough_reason'>> };

/** "Oro: ..." -> "oro"; one label per not-applicable class, in order of appearance. */
function notApplicableLabels(details: ApplicableCoverageInput['etf_details']): string[] {
  const labels: string[] = [];
  for (const detail of details) {
    if (detail.lookthrough_status !== 'not_applicable' || !detail.lookthrough_reason) continue;
    const label = detail.lookthrough_reason.split(':')[0].trim().toLowerCase();
    if (label && !labels.includes(label)) labels.push(label);
  }
  return labels;
}

/**
 * TASK-52: coverage of the applicable (equity) part, with the not-applicable
 * and missing shares. Null for a response without the TASK-52 fields.
 */
export function applicableCoverageText(xray: ApplicableCoverageInput): string | null {
  if (xray.applicable_lookthrough_coverage_pct === undefined) return null;
  const parts: string[] = [
    xray.applicable_lookthrough_coverage_pct === null
      ? 'Look-through azionario non applicabile'
      : `Scomposto il ${formatPctIt(xray.applicable_lookthrough_coverage_pct)} della parte azionaria`,
  ];
  const notApplicable = xray.not_applicable_pct ?? 0;
  if (notApplicable > 0) {
    const labels = notApplicableLabels(xray.etf_details);
    parts.push(`${formatPctIt(notApplicable)} non applicabile${labels.length ? ` (${labels.join(', ')})` : ''}`);
  }
  const missing = xray.missing_pct ?? 0;
  if (missing > 0) parts.push(`${formatPctIt(missing)} con dati mancanti`);
  return parts.join('; ');
}

/** Per-position badge: "non applicabile" vs "dati mancanti" (none when data is available). */
export function lookthroughStatusBadge(
  status: XRayLookthroughStatus | undefined,
): { label: string; color: string } | null {
  if (status === 'not_applicable') return { label: 'non applicabile', color: 'gray' };
  if (status === 'missing') return { label: 'dati mancanti', color: 'orange' };
  return null;
}

/**
 * Top buckets of a distribution, the rest grouped in "Altri" and the
 * unclassified share always last, so the rows still sum to 100.
 */
export function exposureRows(dist: Record<string, number>, limit = 8): Array<[string, number, boolean]> {
  const named = Object.entries(dist)
    .filter(([key, value]) => key !== UNCLASSIFIED_LABEL && value > 0)
    .sort((a, b) => b[1] - a[1]);
  const rows: Array<[string, number, boolean]> = named.slice(0, limit).map(([k, v]) => [k, v, false]);
  const rest = named.slice(limit).reduce((sum, [, v]) => sum + v, 0);
  if (rest > 0) rows.push(['Altri', Math.round(rest * 100) / 100, false]);
  const unclassified = dist[UNCLASSIFIED_LABEL] ?? 0;
  if (unclassified > 0) rows.push([UNCLASSIFIED_LABEL, unclassified, true]);
  return rows;
}
