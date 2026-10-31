import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { usePortfolios } from '../components/dashboard/hooks/queries';
import type { Portfolio } from '../services/api';
import {
  aggregateScope,
  isAggregateScope,
  normalizeScope,
  portfolioScopeKey,
  portfoliosAvailableForAggregate,
  resolveScopeBaseCurrency,
  sanitizeScope,
  scopePortfolios,
  singleScope,
  toggleScopePortfolio,
  type PortfolioScope,
} from './portfolioScope';

// ---- Storage (every access guarded: private mode, blocked storage, quota) ----

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the scope still works for this session.
  }
}

function parseJson(raw: string | null): unknown {
  if (raw == null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Scope saved in the browser. Without the shared key yet, it is migrated from
 * the per-page keys: the FIRE aggregate selection when FIRE was in aggregate
 * mode (with at least two ids), otherwise the Dashboard/Portfolio/Doctor
 * selected portfolio. Null when nothing usable is stored.
 */
export function readStoredPortfolioScope(): PortfolioScope | null {
  const stored = normalizeScope(parseJson(readStorage(STORAGE_KEYS.portfolioScope)));
  if (stored) return stored;

  if (readStorage(STORAGE_KEYS.fireScopeMode) === 'aggregate') {
    const fireIds = parseJson(readStorage(STORAGE_KEYS.fireAggregatePortfolioIds));
    const fireScope = Array.isArray(fireIds) ? aggregateScope(fireIds) : null;
    if (isAggregateScope(fireScope)) return fireScope;
  }

  return normalizeScope(readStorage(STORAGE_KEYS.selectedPortfolioId));
}

function writeStoredPortfolioScope(scope: PortfolioScope): void {
  writeStorage(STORAGE_KEYS.portfolioScope, JSON.stringify(scope));
}

// ---- Context ----

export interface PortfolioScopeContextValue {
  /**
   * Current scope. Before the portfolio list has loaded it is the stored scope
   * as is (see `isReady`); afterwards it is always sanitized against the list.
   * Null only when there is nothing stored yet or the user has no portfolios.
   */
  scope: PortfolioScope | null;
  /** Stable React Query key segment of the scope (see `portfolioScopeKey`). */
  scopeKey: number | string | null;
  isAggregate: boolean;
  /** The portfolio list has loaded and `scope` is sanitized against it. */
  isReady: boolean;
  portfolios: Portfolio[];
  /** Portfolios of the scope, in id order. */
  selectedPortfolios: Portfolio[];
  /** Base currency of the scope (shared by all its portfolios). */
  baseCurrency: string | null;
  setScope: (scope: PortfolioScope) => void;
  setSingle: (portfolioId: number) => void;
  /** Aggregate of the given ids; one id left after sanitizing collapses to single. */
  setAggregate: (portfolioIds: number[]) => void;
  /** Add/remove a portfolio from the aggregate (from single mode, adding one starts an aggregate). */
  toggleInAggregate: (portfolioId: number) => void;
  /** Portfolios (default: all loaded) that share the scope's base currency. */
  availableForAggregate: (portfolios?: Portfolio[]) => Portfolio[];
}

const PortfolioScopeContext = createContext<PortfolioScopeContextValue | null>(null);

const NO_PORTFOLIOS: Portfolio[] = [];

/**
 * Holds the portfolio scope shared by the pages, persisted in localStorage.
 *
 * Compatibility until the pages adopt it (TASK-28): explicit changes that end
 * in a single scope also write `STORAGE_KEYS.selectedPortfolioId`, which the
 * pages still read. Sanitizing never writes that key, so the pages' own
 * selection is not touched.
 */
export function PortfolioScopeProvider({ children }: { children: ReactNode }) {
  const { data } = usePortfolios();
  const isReady = data !== undefined;
  const portfolios = data ?? NO_PORTFOLIOS;
  const [rawScope, setRawScope] = useState<PortfolioScope | null>(readStoredPortfolioScope);

  const scope = useMemo(
    () => (isReady ? sanitizeScope(rawScope, portfolios) : rawScope),
    [isReady, portfolios, rawScope],
  );
  const scopeKey = portfolioScopeKey(scope);

  // Persist the sanitized scope once it is known (deleted portfolios dropped).
  useEffect(() => {
    if (isReady && scope) writeStoredPortfolioScope(scope);
  }, [isReady, scope]);

  const apply = useCallback((next: PortfolioScope | null) => {
    if (!next) return;
    setRawScope(next);
    writeStoredPortfolioScope(next);
    if (next.mode === 'single') {
      writeStorage(STORAGE_KEYS.selectedPortfolioId, String(next.id));
    }
  }, []);

  const setScope = useCallback((next: PortfolioScope) => {
    const normalized = normalizeScope(next);
    apply(isReady && normalized ? sanitizeScope(normalized, portfolios) : normalized);
  }, [apply, isReady, portfolios]);

  const setSingle = useCallback((portfolioId: number) => {
    setScope(singleScope(portfolioId));
  }, [setScope]);

  const setAggregate = useCallback((portfolioIds: number[]) => {
    const next = aggregateScope(portfolioIds);
    if (next) setScope(next);
  }, [setScope]);

  const toggleInAggregate = useCallback((portfolioId: number) => {
    apply(toggleScopePortfolio(scope, portfolioId, portfolios));
  }, [apply, portfolios, scope]);

  const availableForAggregate = useCallback(
    (list?: Portfolio[]) => portfoliosAvailableForAggregate(scope, list ?? portfolios),
    [portfolios, scope],
  );

  const value = useMemo<PortfolioScopeContextValue>(() => ({
    scope,
    scopeKey,
    isAggregate: isAggregateScope(scope),
    isReady,
    portfolios,
    selectedPortfolios: scopePortfolios(scope, portfolios),
    baseCurrency: resolveScopeBaseCurrency(scope, portfolios),
    setScope,
    setSingle,
    setAggregate,
    toggleInAggregate,
    availableForAggregate,
  }), [scope, scopeKey, isReady, portfolios, setScope, setSingle, setAggregate, toggleInAggregate, availableForAggregate]);

  return <PortfolioScopeContext.Provider value={value}>{children}</PortfolioScopeContext.Provider>;
}

/** The shared portfolio scope. Must be used under PortfolioScopeProvider. */
export function usePortfolioScope(): PortfolioScopeContextValue {
  const context = useContext(PortfolioScopeContext);
  if (!context) throw new Error('usePortfolioScope must be used within a PortfolioScopeProvider');
  return context;
}

/** The shared portfolio scope, or null outside PortfolioScopeProvider. */
export function useOptionalPortfolioScope(): PortfolioScopeContextValue | null {
  return useContext(PortfolioScopeContext);
}
