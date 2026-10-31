// API errors of the aggregate routes (`/portfolios/aggregate/...`) turned into
// short Italian messages, and detection of the errors that mean the stored
// scope is stale (a portfolio deleted or changed elsewhere).

import { ApiRequestError } from '../services/api/client';
import {
  AGGREGATE_ERROR_EMPTY,
  AGGREGATE_ERROR_MIXED_CURRENCY,
  AGGREGATE_ERROR_NOT_FOUND,
  AGGREGATE_ERROR_TOO_MANY,
} from './aggregateLabels';

// Fixed messages of the backend scope checks (app/repository/_scope.py, routes_aggregate.py).
const NOT_FOUND_MESSAGE = 'Portfolio non trovato';

export type AggregateScopeErrorKind = 'not_found' | 'mixed_currency' | 'empty' | 'too_many';

/** Kind of scope error of an aggregate request, or null for any other error. */
export function aggregateScopeErrorKind(error: unknown): AggregateScopeErrorKind | null {
  if (!(error instanceof ApiRequestError)) return null;
  const message = error.message.toLowerCase();
  if (error.status === 404 && error.message === NOT_FOUND_MESSAGE) return 'not_found';
  if (error.status !== 400) return null;
  if (message.includes('valuta base')) return 'mixed_currency';
  if (message.includes('al massimo')) return 'too_many';
  if (message.includes('almeno un portafoglio')) return 'empty';
  return null;
}

/** Friendly message for an aggregate scope error; other errors keep their message. */
export function friendlyAggregateError(error: unknown): string | null {
  switch (aggregateScopeErrorKind(error)) {
    case 'not_found':
      return AGGREGATE_ERROR_NOT_FOUND;
    case 'mixed_currency':
      return AGGREGATE_ERROR_MIXED_CURRENCY;
    case 'too_many':
      return AGGREGATE_ERROR_TOO_MANY;
    case 'empty':
      return AGGREGATE_ERROR_EMPTY;
    default:
      return error instanceof Error ? error.message : null;
  }
}

/** True for a React Query key of an aggregate scope (`[prefix, 'aggregate:1,2', ...]`). */
export function isAggregateQueryKey(queryKey: readonly unknown[]): boolean {
  return typeof queryKey[1] === 'string' && queryKey[1].startsWith('aggregate:');
}

/**
 * Message a page shows for a query error. Aggregate scope errors return null:
 * the scope context recovers from them and `AggregateScopeNotice` explains
 * what happened, so the raw API message is not repeated on the page.
 */
export function pageQueryError(error: unknown): string | null {
  if (error == null) return null;
  if (aggregateScopeErrorKind(error)) return null;
  return error instanceof Error ? error.message : null;
}
