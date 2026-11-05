import { describe, expect, it } from 'vitest';
import { formatDate, formatDateTime } from './policyFormat';

describe('date formatting of backend values', () => {
  it('shows a date-only value (quote_as_of) as that calendar date, without a made-up time', () => {
    expect(formatDateTime('2026-11-05')).toBe('05/11/2026');
    expect(formatDate('2026-11-05')).toBe('05/11/2026');
  });

  it('keeps date and time for full timestamps', () => {
    expect(formatDateTime('2026-11-05T10:30:00Z')).toMatch(/^\d{2}\/\d{2}\/2026,? \d{2}:\d{2}$/);
  });

  it('returns N/D without a value', () => {
    expect(formatDateTime(null)).toBe('N/D');
  });
});
