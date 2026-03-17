import { STORAGE_KEYS } from './constants';

const PRIVACY_MASK = '******';

const isPrivacyModeEnabled = () => {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled) === 'true';
};

export const formatNum = (value: number, decimals = 2) =>
  new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);

export const formatPct = (value: number) => `${value >= 0 ? '+' : ''}${formatNum(value, 2)}%`;

export const getVariationColor = (value: number) => (value > 0 ? 'green' : value < 0 ? 'red' : 'gray');

export const formatMoney = (value: number, currency = 'EUR', withSign = false) => {
  if (isPrivacyModeEnabled()) return PRIVACY_MASK;
  const formatted = new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(Math.abs(value));
  if (!withSign) return formatted;
  return `${value > 0 ? '+' : value < 0 ? '-' : ''}${formatted}`;
};

/**
 * Null-safe variant of formatMoney — returns 'N/D' for null/undefined/non-finite values.
 */
export const formatMoneyOrNA = (value: number | null | undefined, currency?: string | null) => {
  if (isPrivacyModeEnabled()) return PRIVACY_MASK;
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency: currency || 'EUR',
    maximumFractionDigits: 2,
  }).format(value);
};

export const formatTransactionSideLabel = (side: string) => {
  switch (side) {
    case 'buy': return 'Acquisto';
    case 'sell': return 'Vendita';
    case 'dividend': return 'Dividendo';
    case 'deposit': return 'Deposito';
    case 'withdrawal': return 'Prelievo';
    case 'fee': return 'Commissione';
    case 'interest': return 'Interesse';
    default: return side;
  }
};

export const formatGrossTotal = (quantity: number | string, price: number | string): string => {
  if (isPrivacyModeEnabled()) return PRIVACY_MASK;
  const toNum = (v: number | string | null | undefined): number | null => {
    if (typeof v === 'number') return Number.isFinite(v) ? v : null;
    if (typeof v === 'string') {
      const trimmed = v.trim();
      if (!trimmed) return null;
      const parsed = Number(trimmed.replace(',', '.'));
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  };
  const q = toNum(quantity);
  const p = toNum(price);
  if (q == null || p == null) return '';
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(q * p);
};

export const getTransactionSideColor = (side: string) => {
  switch (side) {
    case 'buy': return 'teal';
    case 'sell': return 'orange';
    case 'dividend': return 'blue';
    default: return 'gray';
  }
};

export const formatShortDate = (value?: string | null) => {
  if (!value) return null;
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return null;
  return dt.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

export const formatDateTime = (value?: string | null) => {
  if (!value) return 'N/D';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return 'N/D';
  return dt.toLocaleString('it-IT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};
