import type { FireOneOffExpense } from '../../services/api';

export interface FireTargetInput {
  annualExpenses: number;
  safeWithdrawalRatePct: number;
  /** Capital that must never be spent, in today's money. */
  capitalFloor: number;
  pensionAnnual: number;
  pensionStartAge: number | null;
  oneOffExpenses: FireOneOffExpense[];
  currentAge: number | null;
}

export interface FireTargetBreakdown {
  total: number;
  spendingCapital: number;
  pensionBridge: number;
  capitalFloor: number;
  oneOffReserve: number;
}

export interface AccumulationInput extends FireTargetInput {
  startCapital: number;
  annualContribution: number;
  contributionGrowthPct: number;
  annualReturnPct: number;
}

const MAX_SIMULATION_YEARS = 100;

/**
 * Capital needed at `fireAge` (today's money): spending funded at the SWR,
 * the pension bridge until the pension starts, the untouchable floor and the
 * one-off expenses that fall after FIRE. Without ages every pension is treated
 * as active at FIRE and every one-off expense is reserved.
 */
export function computeFireTarget(input: FireTargetInput, fireAge: number | null): FireTargetBreakdown | null {
  const expenses = Math.max(0, input.annualExpenses);
  if (expenses <= 0 || input.safeWithdrawalRatePct <= 0) return null;

  const pension = Math.min(Math.max(0, input.pensionAnnual), expenses);
  const spendingCapital = (expenses - pension) / (input.safeWithdrawalRatePct / 100);
  const bridgeYears = pension > 0 && input.pensionStartAge != null && fireAge != null
    ? Math.max(0, input.pensionStartAge - fireAge)
    : 0;
  const pensionBridge = pension * bridgeYears;
  const capitalFloor = Math.max(0, input.capitalFloor);
  const oneOffReserve = input.oneOffExpenses
    .filter((expense) => {
      if (input.currentAge == null || fireAge == null) return true;
      return expense.age >= fireAge;
    })
    .reduce((sum, expense) => sum + Math.max(0, expense.amount), 0);

  return {
    total: spendingCapital + pensionBridge + capitalFloor + oneOffReserve,
    spendingCapital,
    pensionBridge,
    capitalFloor,
    oneOffReserve,
  };
}

function oneOffAtAge(input: FireTargetInput, age: number): number {
  return input.oneOffExpenses
    .filter((expense) => expense.age === age)
    .reduce((sum, expense) => sum + Math.max(0, expense.amount), 0);
}

function contributionForYear(input: AccumulationInput, year: number): number {
  return Math.max(0, input.annualContribution) * (1 + input.contributionGrowthPct / 100) ** (year - 1);
}

/** Capital after `years` of accumulation; one-offs are paid at the start of their year. */
function capitalAfterYears(input: AccumulationInput, years: number, contributionScale = 1): number {
  const r = input.annualReturnPct / 100;
  let capital = input.startCapital;
  for (let year = 1; year <= years; year += 1) {
    const oneOff = input.currentAge != null ? oneOffAtAge(input, input.currentAge + year - 1) : 0;
    capital = (capital - oneOff) * (1 + r) + contributionForYear(input, year) * contributionScale;
  }
  return capital;
}

/** Closed-form time to grow `current` into `target` with a constant end-of-year contribution. */
export function solveYearsToTarget(target: number, current: number, annualContribution: number, annualReturnPct: number): number | null {
  if (!Number.isFinite(target) || !Number.isFinite(current) || target <= 0) return null;
  if (current >= target) return 0;
  if (!Number.isFinite(annualContribution) || annualContribution < 0) return null;

  const r = annualReturnPct / 100;
  if (r === 0) {
    if (annualContribution <= 0) return null;
    return Math.max(0, (target - current) / annualContribution);
  }

  const denominator = current * r + annualContribution;
  const numerator = target * r + annualContribution;
  if (denominator <= 0 || numerator <= denominator) {
    return annualContribution > 0 ? Math.max(0, Math.log(numerator / denominator) / Math.log(1 + r)) : null;
  }

  const years = Math.log(numerator / denominator) / Math.log(1 + r);
  return Number.isFinite(years) && years >= 0 ? years : null;
}

/**
 * Years until capital reaches the FIRE target. The target moves with the
 * candidate FIRE age (pension bridge, one-offs after FIRE), so the plan is
 * stepped year by year and the final partial year is solved in closed form.
 */
export function estimateYearsToFire(input: AccumulationInput): number | null {
  const targetAt = (year: number) => computeFireTarget(input, input.currentAge != null ? input.currentAge + year : null)?.total ?? null;

  const initialTarget = targetAt(0);
  if (initialTarget == null) return null;
  if (input.startCapital >= initialTarget) return 0;

  const r = input.annualReturnPct / 100;
  let capital = input.startCapital;
  for (let year = 1; year <= MAX_SIMULATION_YEARS; year += 1) {
    const target = targetAt(year);
    if (target == null) return null;
    const oneOff = input.currentAge != null ? oneOffAtAge(input, input.currentAge + year - 1) : 0;
    const startOfYear = capital - oneOff;
    const contribution = contributionForYear(input, year);
    const endOfYear = startOfYear * (1 + r) + contribution;
    if (endOfYear >= target) {
      const fraction = solveYearsToTarget(target, startOfYear, contribution, input.annualReturnPct);
      return year - 1 + Math.min(1, Math.max(0, fraction ?? 1));
    }
    capital = endOfYear;
  }
  return null;
}

/** Initial annual contribution (growing at `contributionGrowthPct`) needed to reach FIRE at `targetAge`. */
export function solveRequiredContribution(input: AccumulationInput, targetAge: number): number | null {
  if (input.currentAge == null || targetAge <= input.currentAge) return null;
  const years = targetAge - input.currentAge;
  const target = computeFireTarget(input, targetAge)?.total;
  if (target == null) return null;

  // Final capital is linear in the contribution: base + contribution * slope.
  const base = capitalAfterYears(input, years, 0);
  if (base >= target) return 0;
  const slope = (capitalAfterYears({ ...input, annualContribution: 1 }, years, 1) - base);
  if (slope <= 0) return null;
  return Math.max(0, (target - base) / slope);
}
