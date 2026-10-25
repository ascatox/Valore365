import { getExchangeStatus } from './exchangeSchedules';

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
