import { getExchangeStatus, sortByOpenExchange, sortCategoriesByOpenExchange } from './exchangeSchedules';

describe('getExchangeStatus', () => {
  // Monday 26 October 2026: New York on EDT (UTC-4), Milan on CET (UTC+1).
  it('reports an exchange open during its session', () => {
    expect(getExchangeStatus('^GSPC', new Date('2026-10-26T15:00:00Z'))).toEqual({
      exchange: 'NYSE',
      open: true,
      closedReason: null,
    });
    expect(getExchangeStatus('FTSEMIB.MI', new Date('2026-10-26T08:30:00Z'))?.open).toBe(true);
  });

  it('reports why an exchange is closed', () => {
    expect(getExchangeStatus('^GSPC', new Date('2026-10-26T22:00:00Z'))).toEqual({
      exchange: 'NYSE',
      open: false,
      closedReason: 'orario di chiusura',
    });
    expect(getExchangeStatus('FTSEMIB.MI', new Date('2026-10-24T10:00:00Z'))?.closedReason).toBe('weekend');
  });

  it('keeps crypto always open and ignores unknown symbols', () => {
    expect(getExchangeStatus('BTC-USD', new Date('2026-10-24T03:00:00Z'))?.open).toBe(true);
    expect(getExchangeStatus('UNKNOWN', new Date('2026-10-26T15:00:00Z'))).toBeNull();
  });
});

describe('sortByOpenExchange', () => {
  const items = [{ symbol: '^GSPC' }, { symbol: 'FTSEMIB.MI' }, { symbol: 'EURIBOR3M' }, { symbol: 'BTC-USD' }];

  it('puts open exchanges first and keeps the order otherwise', () => {
    // Monday 26 October 2026, 08:30 UTC: Milan open, New York closed.
    expect(sortByOpenExchange(items, new Date('2026-10-26T08:30:00Z')).map((item) => item.symbol)).toEqual([
      'FTSEMIB.MI', 'BTC-USD', '^GSPC', 'EURIBOR3M',
    ]);
  });

  it('keeps the order when every exchange is closed', () => {
    const closed = [{ symbol: '^GSPC' }, { symbol: 'FTSEMIB.MI' }, { symbol: 'EURIBOR3M' }];
    expect(sortByOpenExchange(closed, new Date('2026-10-24T10:00:00Z'))).toEqual(closed);
  });
});

describe('sortCategoriesByOpenExchange', () => {
  it('puts categories with an open exchange first', () => {
    const categories = [
      { category: 'indices', items: [{ symbol: '^GSPC' }, { symbol: 'FTSEMIB.MI' }] },
      { category: 'rates', items: [{ symbol: 'EURIBOR3M' }] },
      { category: 'crypto', items: [{ symbol: 'BTC-USD' }] },
    ];
    // Saturday: only crypto trades.
    const sorted = sortCategoriesByOpenExchange(categories, new Date('2026-10-24T10:00:00Z'));
    expect(sorted.map((category) => category.category)).toEqual(['crypto', 'indices', 'rates']);
    expect(sorted[1].items).toEqual(categories[0].items);
  });
});
