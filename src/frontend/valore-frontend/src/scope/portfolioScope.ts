import type { Portfolio } from '../services/api/types';

/**
 * Which portfolios a page shows: one portfolio, or the virtual aggregate of
 * several portfolios with the same base currency.
 *
 * Aggregate ids are always sorted, unique and at least two: an aggregate of
 * one portfolio collapses to `single` (see `aggregateScope`).
 */
export type PortfolioScope =
  | { mode: 'single'; id: number }
  | { mode: 'aggregate'; ids: number[] };

export type AggregatePortfolioScope = Extract<PortfolioScope, { mode: 'aggregate' }>;
export type SinglePortfolioScope = Extract<PortfolioScope, { mode: 'single' }>;

/** What the query hooks accept: a bare id (today's callers), a scope, or nothing yet. */
export type PortfolioScopeInput = number | PortfolioScope | null | undefined;

/** Same limit as the backend (`MAX_AGGREGATE_PORTFOLIOS`). */
export const MAX_AGGREGATE_PORTFOLIOS = 20;

const AGGREGATE_KEY_PREFIX = 'aggregate:';

function toPortfolioId(value: unknown): number | null {
  const parsed = typeof value === 'string' && value.trim() !== '' ? Number(value) : value;
  return typeof parsed === 'number' && Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

/** Positive integer ids (numbers or numeric strings), deduplicated and sorted ascending. */
export function normalizePortfolioIds(ids: Iterable<unknown>): number[] {
  const unique = new Set<number>();
  for (const value of ids) {
    const id = toPortfolioId(value);
    if (id != null) unique.add(id);
  }
  return [...unique].sort((left, right) => left - right);
}

export function singleScope(id: number): SinglePortfolioScope {
  return { mode: 'single', id };
}

/**
 * Scope for a set of ids: normalized, capped at MAX_AGGREGATE_PORTFOLIOS,
 * `single` when only one id is left, `null` when none.
 */
export function aggregateScope(ids: Iterable<unknown>): PortfolioScope | null {
  const normalized = normalizePortfolioIds(ids).slice(0, MAX_AGGREGATE_PORTFOLIOS);
  if (normalized.length === 0) return null;
  if (normalized.length === 1) return singleScope(normalized[0]);
  return { mode: 'aggregate', ids: normalized };
}

/** A well-formed scope from any value (stored JSON, a bare id, ...), or null. */
export function normalizeScope(value: unknown): PortfolioScope | null {
  if (value == null) return null;
  const id = toPortfolioId(value);
  if (id != null) return singleScope(id);
  if (typeof value !== 'object') return null;
  const candidate = value as { mode?: unknown; id?: unknown; ids?: unknown };
  if (candidate.mode === 'single') {
    const singleId = toPortfolioId(candidate.id);
    return singleId != null ? singleScope(singleId) : null;
  }
  if (candidate.mode === 'aggregate' && Array.isArray(candidate.ids)) {
    return aggregateScope(candidate.ids);
  }
  return null;
}

/** Hook input → scope. A bare id is a single scope. */
export function toPortfolioScope(input: PortfolioScopeInput): PortfolioScope | null {
  if (input == null) return null;
  if (typeof input === 'number') return toPortfolioId(input) != null ? singleScope(input) : null;
  return normalizeScope(input);
}

export function isAggregateScope(scope: PortfolioScope | null | undefined): scope is AggregatePortfolioScope {
  return scope?.mode === 'aggregate';
}

export function scopePortfolioIds(scope: PortfolioScope | null | undefined): number[] {
  if (!scope) return [];
  return scope.mode === 'single' ? [scope.id] : [...scope.ids];
}

/** The portfolio id when the scope is a single portfolio, null otherwise (aggregate or empty). */
export function singlePortfolioId(input: PortfolioScopeInput): number | null {
  const scope = toPortfolioScope(input);
  return scope?.mode === 'single' ? scope.id : null;
}

export function scopesEqual(left: PortfolioScope | null | undefined, right: PortfolioScope | null | undefined): boolean {
  return portfolioScopeKey(left ?? null) === portfolioScopeKey(right ?? null);
}

/**
 * React Query key segment for a scope. A single portfolio keeps its bare id,
 * so existing keys (`['portfolio-summary', 3]`) and the invalidations that
 * match them do not change; an aggregate is `'aggregate:1,2'` (sorted ids),
 * which can never equal a single entry.
 */
export function portfolioScopeKey(input: PortfolioScopeInput): number | string | null {
  const scope = toPortfolioScope(input);
  if (!scope) return null;
  return scope.mode === 'single' ? scope.id : `${AGGREGATE_KEY_PREFIX}${scope.ids.join(',')}`;
}

/** Whether a query key segment produced by `portfolioScopeKey` covers the given portfolio. */
export function portfolioScopeKeyIncludes(keySegment: unknown, portfolioId: number): boolean {
  if (typeof keySegment === 'number') return keySegment === portfolioId;
  if (typeof keySegment !== 'string' || !keySegment.startsWith(AGGREGATE_KEY_PREFIX)) return false;
  return keySegment
    .slice(AGGREGATE_KEY_PREFIX.length)
    .split(',')
    .some((value) => Number(value) === portfolioId);
}

/** Portfolios of the scope, in scope (id) order; ids missing from the list are skipped. */
export function scopePortfolios(scope: PortfolioScope | null | undefined, portfolios: Portfolio[]): Portfolio[] {
  const byId = new Map(portfolios.map((portfolio) => [portfolio.id, portfolio]));
  return scopePortfolioIds(scope)
    .map((id) => byId.get(id))
    .filter((portfolio): portfolio is Portfolio => portfolio != null);
}

/** Base currency of the scope: that of its first portfolio found in the list. */
export function resolveScopeBaseCurrency(scope: PortfolioScope | null | undefined, portfolios: Portfolio[]): string | null {
  return scopePortfolios(scope, portfolios)[0]?.base_currency ?? null;
}

/**
 * Portfolios that can join the scope's aggregate: those with the scope's base
 * currency. With no scope (or none of its portfolios loaded) all of them.
 */
export function portfoliosAvailableForAggregate(
  scope: PortfolioScope | null | undefined,
  portfolios: Portfolio[],
): Portfolio[] {
  const currency = resolveScopeBaseCurrency(scope, portfolios);
  if (!currency) return portfolios;
  return portfolios.filter((portfolio) => portfolio.base_currency === currency);
}

/**
 * Scope cleaned against the loaded portfolios: deleted ids are dropped, ids
 * whose base currency differs from the first remaining portfolio are dropped,
 * one id left collapses to single, nothing left falls back to the first
 * portfolio. Null only when there are no portfolios.
 */
export function sanitizeScope(scope: PortfolioScope | null | undefined, portfolios: Portfolio[]): PortfolioScope | null {
  const present = scopePortfolios(scope, portfolios);
  const currency = present[0]?.base_currency;
  const sameCurrency = present.filter((portfolio) => portfolio.base_currency === currency);
  const sanitized = aggregateScope(sameCurrency.map((portfolio) => portfolio.id));
  if (sanitized) return sanitized;
  return portfolios.length > 0 ? singleScope(portfolios[0].id) : null;
}

/**
 * Scope after adding or removing a portfolio from the aggregate. From single
 * mode, adding a portfolio makes an aggregate with the current one. Removing
 * the last portfolio, adding one with another base currency, or going past
 * MAX_AGGREGATE_PORTFOLIOS leaves the scope unchanged.
 */
export function toggleScopePortfolio(
  scope: PortfolioScope | null,
  portfolioId: number,
  portfolios: Portfolio[] = [],
): PortfolioScope | null {
  const ids = scopePortfolioIds(scope);
  if (ids.includes(portfolioId)) {
    const remaining = ids.filter((id) => id !== portfolioId);
    return remaining.length ? aggregateScope(remaining) : scope;
  }
  const currency = resolveScopeBaseCurrency(scope, portfolios);
  const candidate = portfolios.find((portfolio) => portfolio.id === portfolioId);
  if (currency && candidate && candidate.base_currency !== currency) return scope;
  if (ids.length >= MAX_AGGREGATE_PORTFOLIOS) return scope;
  return aggregateScope([...ids, portfolioId]);
}
