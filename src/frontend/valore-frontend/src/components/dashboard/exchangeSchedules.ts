export interface ExchangeSchedule {
  exchange: string;
  tz: string;          // IANA timezone
  openHour: number;    // 0-23
  openMin: number;
  closeHour: number;
  closeMin: number;
  weekdays: boolean;   // true = Mon-Fri only
}

export const EXCHANGE_SCHEDULES: Record<string, ExchangeSchedule> = {
  // US indices
  '^GSPC':      { exchange: 'NYSE',      tz: 'America/New_York',  openHour: 9,  openMin: 30, closeHour: 16, closeMin: 0,  weekdays: true },
  '^DJI':       { exchange: 'NYSE',      tz: 'America/New_York',  openHour: 9,  openMin: 30, closeHour: 16, closeMin: 0,  weekdays: true },
  '^IXIC':      { exchange: 'NASDAQ',    tz: 'America/New_York',  openHour: 9,  openMin: 30, closeHour: 16, closeMin: 0,  weekdays: true },
  // European indices
  '^STOXX50E':  { exchange: 'Eurex',     tz: 'Europe/Berlin',     openHour: 9,  openMin: 0,  closeHour: 17, closeMin: 30, weekdays: true },
  'FTSEMIB.MI': { exchange: 'Borsa Italiana', tz: 'Europe/Rome',  openHour: 9,  openMin: 0,  closeHour: 17, closeMin: 30, weekdays: true },
  '^FTSE':      { exchange: 'LSE',       tz: 'Europe/London',     openHour: 8,  openMin: 0,  closeHour: 16, closeMin: 30, weekdays: true },
  '^GDAXI':     { exchange: 'XETRA',     tz: 'Europe/Berlin',     openHour: 9,  openMin: 0,  closeHour: 17, closeMin: 30, weekdays: true },
  // Japan
  '^N225':      { exchange: 'TSE',       tz: 'Asia/Tokyo',        openHour: 9,  openMin: 0,  closeHour: 15, closeMin: 0,  weekdays: true },
  // Volatility
  '^VIX':       { exchange: 'CBOE',      tz: 'America/Chicago',   openHour: 8,  openMin: 30, closeHour: 15, closeMin: 15, weekdays: true },
  // Commodities (CME futures: Sun 17:00 – Fri 16:00 CT, with daily break 16:00-17:00)
  'GC=F':       { exchange: 'CME',       tz: 'America/Chicago',   openHour: 17, openMin: 0,  closeHour: 16, closeMin: 0,  weekdays: true },
  'SI=F':       { exchange: 'CME',       tz: 'America/Chicago',   openHour: 17, openMin: 0,  closeHour: 16, closeMin: 0,  weekdays: true },
  'CL=F':       { exchange: 'CME',       tz: 'America/Chicago',   openHour: 17, openMin: 0,  closeHour: 16, closeMin: 0,  weekdays: true },
  // Crypto – always open
  'BTC-USD':    { exchange: 'Crypto',    tz: 'UTC',               openHour: 0,  openMin: 0,  closeHour: 0,  closeMin: 0,  weekdays: false },
  'ETH-USD':    { exchange: 'Crypto',    tz: 'UTC',               openHour: 0,  openMin: 0,  closeHour: 0,  closeMin: 0,  weekdays: false },
  'SOL-USD':    { exchange: 'Crypto',    tz: 'UTC',               openHour: 0,  openMin: 0,  closeHour: 0,  closeMin: 0,  weekdays: false },
};

export function isExchangeOpen(schedule: ExchangeSchedule, now: Date): boolean {
  // Crypto is always open
  if (!schedule.weekdays && schedule.openHour === 0 && schedule.closeHour === 0) return true;

  // Get current time in the exchange timezone
  const tzTime = new Date(now.toLocaleString('en-US', { timeZone: schedule.tz }));
  const day = tzTime.getDay(); // 0=Sun, 6=Sat
  const hour = tzTime.getHours();
  const min = tzTime.getMinutes();
  const timeInMin = hour * 60 + min;

  const openMin = schedule.openHour * 60 + schedule.openMin;
  const closeMin = schedule.closeHour * 60 + schedule.closeMin;

  // CME-style overnight session (open > close means session spans midnight)
  if (openMin > closeMin) {
    // Closed on Saturday all day; Sunday open from openHour; Friday close at closeHour
    if (day === 6) return false; // Saturday
    if (day === 0) return timeInMin >= openMin; // Sunday: open from 17:00
    if (day === 5) return timeInMin < closeMin; // Friday: close at 16:00
    // Mon-Thu: only closed during daily break (closeMin..openMin)
    return timeInMin >= openMin || timeInMin < closeMin;
  }

  // Standard session: weekdays only, open-close same day
  if (day === 0 || day === 6) return false;
  return timeInMin >= openMin && timeInMin < closeMin;
}

function getClosedReason(schedule: ExchangeSchedule, now: Date): string {
  const tzTime = new Date(now.toLocaleString('en-US', { timeZone: schedule.tz }));
  const day = tzTime.getDay();
  if (day === 0 || day === 6) return 'weekend';
  return 'orario di chiusura';
}

export interface ClosedExchangeInfo {
  exchange: string;
  reason: string;
}

export function getClosedExchanges(symbols: string[], now: Date): ClosedExchangeInfo[] {
  const seen = new Set<string>();
  const result: ClosedExchangeInfo[] = [];

  for (const symbol of symbols) {
    const schedule = EXCHANGE_SCHEDULES[symbol];
    if (!schedule || seen.has(schedule.exchange)) continue;
    seen.add(schedule.exchange);

    if (!isExchangeOpen(schedule, now)) {
      result.push({ exchange: schedule.exchange, reason: getClosedReason(schedule, now) });
    }
  }
  return result;
}
