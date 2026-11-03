/** X-Ray display helpers (TASK-48: look-through coverage, unclassified share, data date). */

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
