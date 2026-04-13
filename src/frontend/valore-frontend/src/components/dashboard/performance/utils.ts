import { formatNum } from '../formatters';

export type PeriodKey = '1m' | '3m' | '6m' | 'ytd' | '1y' | '3y' | 'all';
export type RollingWindowKey = '12' | '36';

export const PERIOD_OPTIONS: Array<{ label: string; value: PeriodKey }> = [
  { label: '1M', value: '1m' },
  { label: '3M', value: '3m' },
  { label: '6M', value: '6m' },
  { label: 'YTD', value: 'ytd' },
  { label: '1Y', value: '1y' },
  { label: '3Y', value: '3y' },
  { label: 'ALL', value: 'all' },
];

export const ROLLING_WINDOW_OPTIONS: Array<{ label: string; value: RollingWindowKey }> = [
  { label: '12M', value: '12' },
  { label: '36M', value: '36' },
];

export const MONTH_LABELS = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

export function kpiColor(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'var(--mantine-color-dimmed)';
  return value >= 0 ? 'var(--mantine-color-green-7)' : 'var(--mantine-color-red-7)';
}

export function periodToStartDate(period: PeriodKey): string | undefined {
  if (period === 'all') return undefined;
  const today = new Date();
  let d: Date;
  switch (period) {
    case '1m': d = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate()); break;
    case '3m': d = new Date(today.getFullYear(), today.getMonth() - 3, today.getDate()); break;
    case '6m': d = new Date(today.getFullYear(), today.getMonth() - 6, today.getDate()); break;
    case 'ytd': d = new Date(today.getFullYear(), 0, 1); break;
    case '1y': d = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate()); break;
    case '3y': d = new Date(today.getFullYear() - 3, today.getMonth(), today.getDate()); break;
    default: return undefined;
  }
  return d.toISOString().slice(0, 10);
}

export function formatChartDate(isoDate: string): string {
  const dt = new Date(isoDate);
  if (Number.isNaN(dt.getTime())) return isoDate;
  return dt.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' });
}

export function formatYearMonth(value: string): string {
  const [year, month] = value.split('-');
  const monthIndex = Number(month) - 1;
  if (!Number.isFinite(monthIndex) || monthIndex < 0 || monthIndex > 11) return value;
  return `${MONTH_LABELS[monthIndex]} ${year.slice(-2)}`;
}

export function formatPctPlain(value: number, decimals = 2): string {
  return `${formatNum(value, decimals)}%`;
}

export function heatmapCellColors(value: number | null, isDark: boolean) {
  if (value == null || !Number.isFinite(value)) {
    return {
      background: isDark ? 'rgba(255,255,255,0.03)' : '#f8fafc',
      color: 'var(--mantine-color-dimmed)',
      border: isDark ? '1px solid rgba(255,255,255,0.05)' : '1px solid rgba(15,23,42,0.06)',
    };
  }

  const intensity = Math.min(Math.abs(value) / 12, 1);
  if (value >= 0) {
    return {
      background: `rgba(34, 197, 94, ${0.16 + intensity * 0.28})`,
      color: isDark ? '#dcfce7' : '#166534',
      border: '1px solid rgba(34,197,94,0.22)',
    };
  }

  return {
    background: `rgba(239, 68, 68, ${0.16 + intensity * 0.28})`,
    color: isDark ? '#fee2e2' : '#991b1b',
    border: '1px solid rgba(239,68,68,0.22)',
  };
}
