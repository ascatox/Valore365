import { describe, expect, it } from 'vitest';
import type { Portfolio } from '../services/api/types';
import {
  MAX_AGGREGATE_PORTFOLIOS,
  aggregateScope,
  isAggregateScope,
  normalizePortfolioIds,
  normalizeScope,
  portfolioScopeKey,
  portfolioScopeKeyIncludes,
  portfoliosAvailableForAggregate,
  resolveScopeBaseCurrency,
  sanitizeScope,
  scopePortfolioIds,
  scopePortfolios,
  scopesEqual,
  singlePortfolioId,
  singleScope,
  toPortfolioScope,
  toggleScopePortfolio,
} from './portfolioScope';

const portfolio = (id: number, base_currency = 'EUR'): Portfolio => ({
  id,
  name: `P${id}`,
  base_currency,
  timezone: 'Europe/Rome',
  target_notional: null,
  cash_balance: 0,
  created_at: '2026-01-01T00:00:00Z',
});

const portfolios = [portfolio(1), portfolio(2), portfolio(3, 'USD'), portfolio(4)];

describe('portfolio scope helpers', () => {
  it('normalizes ids: numeric strings accepted, invalid dropped, deduplicated and sorted', () => {
    expect(normalizePortfolioIds([3, '1', 3, 'x', 0, -2, 1.5, null, ' 2 '])).toEqual([1, 2, 3]);
  });

  it('collapses an aggregate of one portfolio to single and of none to null', () => {
    expect(aggregateScope([5, 2, 5])).toEqual({ mode: 'aggregate', ids: [2, 5] });
    expect(aggregateScope([7, 7])).toEqual({ mode: 'single', id: 7 });
    expect(aggregateScope([])).toBeNull();
  });

  it('caps the aggregate at the backend limit', () => {
    const ids = Array.from({ length: MAX_AGGREGATE_PORTFOLIOS + 5 }, (_, index) => index + 1);
    const scope = aggregateScope(ids);
    expect(scopePortfolioIds(scope)).toHaveLength(MAX_AGGREGATE_PORTFOLIOS);
  });

  it('parses stored values and bare ids', () => {
    expect(normalizeScope({ mode: 'single', id: '4' })).toEqual(singleScope(4));
    expect(normalizeScope({ mode: 'aggregate', ids: [3, 1] })).toEqual({ mode: 'aggregate', ids: [1, 3] });
    expect(normalizeScope({ mode: 'aggregate', ids: [1] })).toEqual(singleScope(1));
    expect(normalizeScope('12')).toEqual(singleScope(12));
    expect(normalizeScope({ mode: 'other' })).toBeNull();
    expect(normalizeScope('abc')).toBeNull();
    expect(toPortfolioScope(9)).toEqual(singleScope(9));
    expect(toPortfolioScope(null)).toBeNull();
  });

  it('tells single and aggregate apart', () => {
    expect(isAggregateScope(aggregateScope([1, 2]))).toBe(true);
    expect(isAggregateScope(singleScope(1))).toBe(false);
    expect(singlePortfolioId(5)).toBe(5);
    expect(singlePortfolioId(aggregateScope([1, 2]))).toBeNull();
  });

  it('builds query keys: bare id for single, sorted ids for aggregate', () => {
    expect(portfolioScopeKey(3)).toBe(3);
    expect(portfolioScopeKey(singleScope(3))).toBe(3);
    expect(portfolioScopeKey({ mode: 'aggregate', ids: [4, 2] })).toBe('aggregate:2,4');
    expect(portfolioScopeKey(null)).toBeNull();
    expect(scopesEqual({ mode: 'aggregate', ids: [4, 2] }, aggregateScope([2, 4]))).toBe(true);
    expect(scopesEqual(singleScope(2), aggregateScope([2, 4]))).toBe(false);
    expect(portfolioScopeKeyIncludes('aggregate:2,4', 4)).toBe(true);
    expect(portfolioScopeKeyIncludes('aggregate:2,4', 3)).toBe(false);
    expect(portfolioScopeKeyIncludes(3, 3)).toBe(true);
  });

  it('resolves portfolios and base currency of the scope', () => {
    expect(scopePortfolios(aggregateScope([4, 1, 99]), portfolios).map((item) => item.id)).toEqual([1, 4]);
    expect(resolveScopeBaseCurrency(singleScope(3), portfolios)).toBe('USD');
    expect(resolveScopeBaseCurrency(null, portfolios)).toBeNull();
    expect(portfoliosAvailableForAggregate(singleScope(1), portfolios).map((item) => item.id)).toEqual([1, 2, 4]);
    expect(portfoliosAvailableForAggregate(null, portfolios)).toHaveLength(4);
  });

  it('sanitizes against the loaded portfolios', () => {
    // Deleted id dropped.
    expect(sanitizeScope(aggregateScope([1, 2, 99]), portfolios)).toEqual({ mode: 'aggregate', ids: [1, 2] });
    // Only one left: back to single.
    expect(sanitizeScope(aggregateScope([2, 99]), portfolios)).toEqual(singleScope(2));
    // Different base currency than the first dropped.
    expect(sanitizeScope(aggregateScope([1, 3, 4]), portfolios)).toEqual({ mode: 'aggregate', ids: [1, 4] });
    // Nothing left: first portfolio.
    expect(sanitizeScope(singleScope(99), portfolios)).toEqual(singleScope(1));
    expect(sanitizeScope(null, portfolios)).toEqual(singleScope(1));
    expect(sanitizeScope(singleScope(1), [])).toBeNull();
  });

  it('toggles portfolios in and out of the aggregate', () => {
    expect(toggleScopePortfolio(singleScope(1), 2, portfolios)).toEqual({ mode: 'aggregate', ids: [1, 2] });
    expect(toggleScopePortfolio(aggregateScope([1, 2]), 2, portfolios)).toEqual(singleScope(1));
    expect(toggleScopePortfolio(aggregateScope([1, 2, 4]), 2, portfolios)).toEqual({ mode: 'aggregate', ids: [1, 4] });
    // Other currency: unchanged.
    expect(toggleScopePortfolio(singleScope(1), 3, portfolios)).toEqual(singleScope(1));
    // Last one cannot be removed.
    expect(toggleScopePortfolio(singleScope(1), 1, portfolios)).toEqual(singleScope(1));
    // From no scope: a single scope.
    expect(toggleScopePortfolio(null, 2, portfolios)).toEqual(singleScope(2));
  });
});
