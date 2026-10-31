import { describe, expect, it } from 'vitest';
import { ApiRequestError } from '../services/api/client';
import { aggregateScopeErrorKind, friendlyAggregateError, isAggregateQueryKey, pageQueryError } from './aggregateErrors';

const apiError = (status: number, message: string, code = 'invalid_request') => new ApiRequestError({ status, code, message });

describe('aggregate scope errors', () => {
  it('recognizes the fixed backend scope messages', () => {
    expect(aggregateScopeErrorKind(apiError(404, 'Portfolio non trovato', 'not_found'))).toBe('not_found');
    expect(aggregateScopeErrorKind(apiError(400, 'I portafogli aggregati devono avere la stessa valuta base'))).toBe('mixed_currency');
    expect(aggregateScopeErrorKind(apiError(400, 'Puoi aggregare al massimo 20 portafogli'))).toBe('too_many');
    expect(aggregateScopeErrorKind(apiError(400, 'Seleziona almeno un portafoglio'))).toBe('empty');
    // Other errors are not scope errors.
    expect(aggregateScopeErrorKind(apiError(404, 'Portafoglio non trovato o vuoto', 'not_found'))).toBeNull();
    expect(aggregateScopeErrorKind(apiError(400, 'Intervallo date non valido', 'bad_request'))).toBeNull();
    expect(aggregateScopeErrorKind(new Error('Portfolio non trovato'))).toBeNull();
  });

  it('turns scope errors into friendly Italian messages and keeps the others', () => {
    expect(friendlyAggregateError(apiError(404, 'Portfolio non trovato', 'not_found'))).toMatch(/non esiste più/);
    expect(friendlyAggregateError(apiError(400, 'I portafogli aggregati devono avere la stessa valuta base'))).toMatch(/valute base diverse/);
    expect(friendlyAggregateError(new Error('Rete non disponibile'))).toBe('Rete non disponibile');
    expect(friendlyAggregateError('x')).toBeNull();
  });

  it('hides scope errors from the page alerts (the scope notice explains them)', () => {
    expect(pageQueryError(null)).toBeNull();
    expect(pageQueryError(apiError(404, 'Portfolio non trovato', 'not_found'))).toBeNull();
    expect(pageQueryError(new Error('Errore server'))).toBe('Errore server');
  });

  it('detects aggregate query keys', () => {
    expect(isAggregateQueryKey(['portfolio-summary', 'aggregate:1,2'])).toBe(true);
    expect(isAggregateQueryKey(['portfolio-summary', 1])).toBe(false);
    expect(isAggregateQueryKey(['portfolios'])).toBe(false);
  });
});
