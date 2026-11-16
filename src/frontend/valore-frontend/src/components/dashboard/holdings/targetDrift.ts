import type { PortfolioTargetDriftItem } from '../../../services/api';
import { formatNum } from '../formatters';

/** Drift from target per asset_id, from GET /portfolios/{id}/target-drift (TASK-88). */
export type TargetDriftMap = Map<number, PortfolioTargetDriftItem>;

/** Beyond 5 points the weight needs attention (same threshold as before). */
export const TARGET_DRIFT_WARNING = 5;

/** The drift base, declared wherever the drift is shown (TASK-85/88, base changed by TASK-95). */
export const TARGET_DRIFT_BASIS =
  'Scostamento sul valore dei soli strumenti con target, liquidità esclusa, come nel ribilanciamento e nel Copilot. La liquidità non si usa mai per ribilanciare.';

/** «+20,00 pt»: non-breaking space, so «pt» never wraps alone (TASK-95). */
export function formatDriftPoints(drift: number): string {
  return `${drift > 0 ? '+' : ''}${formatNum(drift, 2)}\u00a0pt`;
}

export function isDriftWarning(drift: number | null | undefined): boolean {
  return drift != null && Math.abs(drift) > TARGET_DRIFT_WARNING;
}
