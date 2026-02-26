import { STORAGE_KEYS } from './constants';

const PRIVACY_MASK = '******';

const isPrivacyModeEnabled = () => {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled) === 'true';
};

export const formatPct = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;

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
