import { describe, expect, it } from 'vitest';
import {
  computeFireTarget,
  estimateYearsToFire,
  solveRequiredContribution,
  solveYearsToTarget,
  type AccumulationInput,
} from './accumulation';

const baseInput: AccumulationInput = {
  annualExpenses: 30_000,
  safeWithdrawalRatePct: 4,
  capitalFloor: 0,
  pensionAnnual: 0,
  pensionStartAge: null,
  oneOffExpenses: [],
  currentAge: 40,
  startCapital: 200_000,
  annualContribution: 20_000,
  contributionGrowthPct: 0,
  annualReturnPct: 5,
};

describe('computeFireTarget', () => {
  it('matches the plain SWR rule without extras', () => {
    expect(computeFireTarget(baseInput, 55)?.total).toBeCloseTo(750_000);
  });

  it('adds the capital floor on top of the spending capital', () => {
    const target = computeFireTarget({ ...baseInput, capitalFloor: 700_000 }, 55);
    expect(target?.spendingCapital).toBeCloseTo(750_000);
    expect(target?.total).toBeCloseTo(1_450_000);
  });

  it('reduces spending by the pension and bridges the years before it starts', () => {
    const target = computeFireTarget({ ...baseInput, pensionAnnual: 12_000, pensionStartAge: 67 }, 55);
    expect(target?.spendingCapital).toBeCloseTo(18_000 / 0.04);
    expect(target?.pensionBridge).toBeCloseTo(12_000 * 12);
  });

  it('reserves only one-off expenses after FIRE', () => {
    const target = computeFireTarget(
      { ...baseInput, oneOffExpenses: [{ age: 50, amount: 40_000, label: '' }, { age: 60, amount: 25_000, label: '' }] },
      55,
    );
    expect(target?.oneOffReserve).toBe(25_000);
  });

  it('returns null without expenses', () => {
    expect(computeFireTarget({ ...baseInput, annualExpenses: 0 }, 55)).toBeNull();
  });
});

describe('estimateYearsToFire', () => {
  it('matches the closed-form estimate without extras', () => {
    const expected = solveYearsToTarget(750_000, 200_000, 20_000, 5);
    expect(estimateYearsToFire(baseInput)).toBeCloseTo(expected ?? 0, 6);
  });

  it('takes longer with a capital floor and less with contribution growth', () => {
    const plain = estimateYearsToFire(baseInput) ?? 0;
    expect(estimateYearsToFire({ ...baseInput, capitalFloor: 700_000 }) ?? 0).toBeGreaterThan(plain);
    expect(estimateYearsToFire({ ...baseInput, contributionGrowthPct: 3 }) ?? 0).toBeLessThan(plain);
  });

  it('delays FIRE when a one-off expense is paid during accumulation', () => {
    const plain = estimateYearsToFire(baseInput) ?? 0;
    const withExpense = estimateYearsToFire({ ...baseInput, oneOffExpenses: [{ age: 42, amount: 50_000, label: '' }] }) ?? 0;
    expect(withExpense).toBeGreaterThan(plain);
  });

  it('returns zero when the target is already covered', () => {
    expect(estimateYearsToFire({ ...baseInput, startCapital: 2_000_000 })).toBe(0);
  });
});

describe('solveRequiredContribution', () => {
  it('reaches the target exactly at the target age', () => {
    const input = { ...baseInput, capitalFloor: 700_000, contributionGrowthPct: 2 };
    const contribution = solveRequiredContribution(input, 55) ?? 0;
    expect(contribution).toBeGreaterThan(0);
    const years = estimateYearsToFire({ ...input, annualContribution: contribution });
    expect(years).toBeCloseTo(15, 6);
  });

  it('matches the annuity formula without extras', () => {
    const r = 0.05;
    const years = 15;
    const growth = (1 + r) ** years;
    const expected = (750_000 - 200_000 * growth) / ((growth - 1) / r);
    expect(solveRequiredContribution(baseInput, 55)).toBeCloseTo(expected, 6);
  });
});
