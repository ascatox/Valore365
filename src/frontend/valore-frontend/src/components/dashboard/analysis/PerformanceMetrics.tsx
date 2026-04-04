import { useMemo, useState } from 'react';
import {
  Alert,
  Card,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Tooltip,
  UnstyledButton,
} from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer } from 'recharts';
import {
  useGainTimeseries,
  useHallOfFame,
  useMonthlyReturns,
  useMWRTimeseries,
  usePerformanceSummary,
  usePortfolioDrawdown,
  useRollingWindows,
  useTWRTimeseries,
} from '../hooks/queries';
import { formatMoney, formatNum, formatPct, formatShortDate, getVariationColor } from '../formatters';
import { PerformanceChart } from '../summary/PerformanceChart';

type PeriodKey = '1m' | '3m' | '6m' | 'ytd' | '1y' | '3y' | 'all';
type RollingWindowKey = '12' | '36';

interface PerformanceMetricsProps {
  portfolioId: number | null;
}

const PERIOD_OPTIONS: Array<{ label: string; value: PeriodKey }> = [
  { label: '1M', value: '1m' },
  { label: '3M', value: '3m' },
  { label: '6M', value: '6m' },
  { label: 'YTD', value: 'ytd' },
  { label: '1Y', value: '1y' },
  { label: '3Y', value: '3y' },
  { label: 'ALL', value: 'all' },
];

const ROLLING_WINDOW_OPTIONS: Array<{ label: string; value: RollingWindowKey }> = [
  { label: '12M', value: '12' },
  { label: '36M', value: '36' },
];

const MONTH_LABELS = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

function kpiColor(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'var(--mantine-color-dimmed)';
  return value >= 0 ? 'var(--mantine-color-green-7)' : 'var(--mantine-color-red-7)';
}

function periodToStartDate(period: PeriodKey): string | undefined {
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

function formatChartDate(isoDate: string): string {
  const dt = new Date(isoDate);
  if (Number.isNaN(dt.getTime())) return isoDate;
  return dt.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' });
}

function formatYearMonth(value: string): string {
  const [year, month] = value.split('-');
  const monthIndex = Number(month) - 1;
  if (!Number.isFinite(monthIndex) || monthIndex < 0 || monthIndex > 11) return value;
  return `${MONTH_LABELS[monthIndex]} ${year.slice(-2)}`;
}

function formatPctPlain(value: number, decimals = 2): string {
  return `${formatNum(value, decimals)}%`;
}

function heatmapCellColors(value: number | null, isDark: boolean) {
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

function NdTooltip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Tooltip label={label} multiline w={280} withArrow>
      <Text fw={700} style={{ cursor: 'help' }}>{children}</Text>
    </Tooltip>
  );
}

function RankedListCard({
  title,
  items,
}: {
  title: string;
  items: Array<{ label: string; return_pct: number }>;
}) {
  return (
    <Card withBorder radius="md" p="md">
      <Text fw={600} mb="sm">{title}</Text>
      <Stack gap="xs">
        {items.length === 0 ? (
          <Text size="sm" c="dimmed">Dati insufficienti</Text>
        ) : items.map((item, index) => (
          <Group key={`${title}-${item.label}-${index}`} justify="space-between" gap="xs">
            <Text size="sm">{item.label}</Text>
            <Text size="sm" fw={700} c={getVariationColor(item.return_pct)}>
              {formatPct(item.return_pct)}
            </Text>
          </Group>
        ))}
      </Stack>
    </Card>
  );
}

export function PerformanceMetrics({ portfolioId }: PerformanceMetricsProps) {
  const [period, setPeriod] = useState<PeriodKey>('1y');
  const [rollingWindow, setRollingWindow] = useState<RollingWindowKey>('12');
  const startDate = periodToStartDate(period);

  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');
  const gridColor = isDark ? theme.colors.dark[4] : '#e9ecef';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  const { data: summary, isLoading: summaryLoading, error: summaryError } = usePerformanceSummary(portfolioId, period);
  const { data: twrPoints = [], isLoading: twrLoading } = useTWRTimeseries(portfolioId, startDate);
  const { data: gainPoints = [], isLoading: gainLoading } = useGainTimeseries(portfolioId, startDate);
  const { data: mwrPoints = [], isLoading: mwrLoading } = useMWRTimeseries(portfolioId, startDate);
  const { data: monthlyReturns, isLoading: monthlyLoading } = useMonthlyReturns(portfolioId, startDate);
  const { data: drawdown, isLoading: drawdownLoading } = usePortfolioDrawdown(portfolioId, startDate);
  const { data: rolling, isLoading: rollingLoading } = useRollingWindows(portfolioId, Number(rollingWindow), 2, startDate);
  const { data: hallOfFame, isLoading: hallLoading } = useHallOfFame(portfolioId, 5, startDate);

  const loading = summaryLoading;
  const chartsLoading = twrLoading || gainLoading || mwrLoading;
  const error = summaryError instanceof Error ? summaryError.message : null;

  const currency = 'EUR';

  const dualChartData = useMemo(() => {
    const dateMap = new Map<string, { date: string; gain?: number; twr?: number }>();
    for (const p of gainPoints) {
      const key = p.date;
      const entry = dateMap.get(key) ?? { date: formatChartDate(p.date) };
      entry.gain = p.absolute_gain;
      dateMap.set(key, entry);
    }
    for (const p of twrPoints) {
      const key = p.date;
      const entry = dateMap.get(key) ?? { date: formatChartDate(p.date) };
      entry.twr = p.cumulative_twr_pct;
      dateMap.set(key, entry);
    }
    return Array.from(dateMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([, value]) => value);
  }, [gainPoints, twrPoints]);

  const [showGain, setShowGain] = useState(true);
  const [showTwr, setShowTwr] = useState(true);

  const lastGain = gainPoints.length ? gainPoints[gainPoints.length - 1].absolute_gain : null;
  const lastTwr = twrPoints.length ? twrPoints[twrPoints.length - 1].cumulative_twr_pct : null;
  const gainChartColor = lastGain != null && lastGain >= 0 ? '#16a34a' : '#dc2626';
  const twrChartColor = lastTwr != null && lastTwr >= 0 ? '#2563eb' : '#9333ea';

  const mwrChartData = useMemo(
    () => mwrPoints
      .filter((p) => p.cumulative_mwr_pct != null)
      .map((p) => ({
        rawDate: p.date,
        date: formatChartDate(p.date),
        value: p.cumulative_mwr_pct as number,
      })),
    [mwrPoints],
  );

  const monthlyMatrix = useMemo(() => {
    const cells = monthlyReturns?.cells ?? [];
    const yearlyMap = new Map((monthlyReturns?.yearly_returns ?? []).map((item) => [item.year, item.return_pct]));
    const rowsMap = new Map<number, Record<number, number>>();
    for (const cell of cells) {
      const yearRow = rowsMap.get(cell.year) ?? {};
      yearRow[cell.month] = cell.return_pct;
      rowsMap.set(cell.year, yearRow);
    }

    return Array.from(rowsMap.entries())
      .sort((a, b) => b[0] - a[0])
      .map(([year, months]) => ({
        year,
        months,
        yearReturn: yearlyMap.get(year) ?? null,
      }));
  }, [monthlyReturns]);

  const drawdownChartData = useMemo(
    () => (drawdown?.points ?? []).map((point) => ({
      rawDate: point.date,
      date: formatChartDate(point.date),
      value: point.drawdown_pct,
    })),
    [drawdown],
  );

  const rollingCagrData = useMemo(
    () => (rolling?.points ?? [])
      .filter((point) => point.cagr_pct != null)
      .map((point) => ({
        rawDate: point.date,
        date: formatYearMonth(point.date),
        value: point.cagr_pct as number,
      })),
    [rolling],
  );

  const rollingVolData = useMemo(
    () => (rolling?.points ?? [])
      .filter((point) => point.volatility_pct != null)
      .map((point) => ({
        rawDate: point.date,
        date: formatYearMonth(point.date),
        value: point.volatility_pct as number,
      })),
    [rolling],
  );

  const rollingSharpeData = useMemo(
    () => (rolling?.points ?? [])
      .filter((point) => point.sharpe_ratio != null)
      .map((point) => ({
        rawDate: point.date,
        date: formatYearMonth(point.date),
        value: point.sharpe_ratio as number,
      })),
    [rolling],
  );

  const rollingLatest = rolling?.points.length ? rolling.points[rolling.points.length - 1] : null;

  const mwrStats = useMemo(() => {
    if (!mwrChartData.length) return undefined;
    const last = mwrChartData[mwrChartData.length - 1].value;
    return [{ label: 'MWR', value: formatPct(last), color: getVariationColor(last) }];
  }, [mwrChartData]);

  const mwrColor = useMemo(() => {
    if (!mwrChartData.length) return '#228be6';
    const last = mwrChartData[mwrChartData.length - 1].value;
    return last >= 0 ? '#16a34a' : '#dc2626';
  }, [mwrChartData]);

  return (
    <Stack gap="md">
      <Card withBorder radius="md" p="md" shadow="sm">
        <Group justify="space-between" mb="sm" wrap="wrap" gap="xs">
          <Text fw={600}>Performance</Text>
          <SegmentedControl
            size="xs"
            value={period}
            onChange={(value) => setPeriod((value as PeriodKey) ?? '1y')}
            data={PERIOD_OPTIONS}
          />
        </Group>

        {error && <Alert color="red" mb="sm">{error}</Alert>}

        {loading && (
          <Group mb="sm" gap="xs">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">Calcolo metriche in corso...</Text>
          </Group>
        )}

        <SimpleGrid cols={{ base: 2, md: 3 }} spacing="sm">
          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Netto Investito</Text>
            <Text fw={700}>{summary ? formatMoney(summary.net_invested, currency) : (
              <NdTooltip label="Dati insufficienti per calcolare il netto investito">N/D</NdTooltip>
            )}</Text>
          </Card>

          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Versato</Text>
            <Text fw={700}>{summary ? formatMoney(summary.total_deposits, currency) : (
              <NdTooltip label="Nessun deposito registrato nel periodo selezionato">N/D</NdTooltip>
            )}</Text>
          </Card>

          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Prelevato</Text>
            <Text fw={700}>{summary ? formatMoney(summary.total_withdrawals, currency) : (
              <NdTooltip label="Nessun prelievo registrato nel periodo selezionato">N/D</NdTooltip>
            )}</Text>
          </Card>

          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Guadagno Assoluto</Text>
            {summary ? (
              <Text fw={700} style={{ color: kpiColor(summary.absolute_gain) }}>
                {formatMoney(summary.absolute_gain, currency)}
              </Text>
            ) : (
              <NdTooltip label="Dati insufficienti per calcolare il guadagno assoluto">N/D</NdTooltip>
            )}
          </Card>

          <Card withBorder radius="md" p="sm">
            <Tooltip label="Time-Weighted Return — rendimento del portafoglio al netto dei flussi di cassa" multiline w={280} withArrow>
              <Text size="sm" c="dimmed" style={{ cursor: 'help' }}>TWR</Text>
            </Tooltip>
            {summary?.twr?.twr_pct != null ? (
              <Text fw={700} style={{ color: kpiColor(summary.twr.twr_pct) }}>
                {formatPct(summary.twr.twr_pct)}
              </Text>
            ) : (
              <NdTooltip label="Dati insufficienti o assenza di prezzi giornalieri per il calcolo del Time-Weighted Return">N/D</NdTooltip>
            )}
          </Card>

          <Card withBorder radius="md" p="sm">
            <Tooltip label="Money-Weighted Return — rendimento ponderato per i flussi di cassa dell'investitore" multiline w={280} withArrow>
              <Text size="sm" c="dimmed" style={{ cursor: 'help' }}>MWR</Text>
            </Tooltip>
            {summary?.mwr?.mwr_pct != null ? (
              <Text fw={700} style={{ color: kpiColor(summary.mwr.mwr_pct) }}>
                {formatPct(summary.mwr.mwr_pct)}
              </Text>
            ) : (
              <NdTooltip label="Dati insufficienti o assenza di flussi di cassa per il calcolo del Money-Weighted Return">N/D</NdTooltip>
            )}
          </Card>
        </SimpleGrid>
      </Card>

      <Card withBorder radius="md" p="md" shadow="sm">
        <Group justify="space-between" mb="xs" align="center" wrap="wrap" gap="xs">
          <Group gap="xs">
            <Text fw={600} size="sm">Guadagno & TWR</Text>
            {lastGain != null && (
              <UnstyledButton onClick={() => setShowGain((value) => !value)}>
                <Text
                  size="xs"
                  fw={600}
                  c={showGain ? getVariationColor(lastGain) : 'dimmed'}
                  td={showGain ? undefined : 'line-through'}
                  style={{ cursor: 'pointer' }}
                >
                  Guadagno: {formatMoney(lastGain, currency, true)}
                </Text>
              </UnstyledButton>
            )}
            {lastTwr != null && (
              <UnstyledButton onClick={() => setShowTwr((value) => !value)}>
                <Text
                  size="xs"
                  fw={600}
                  c={showTwr ? getVariationColor(lastTwr) : 'dimmed'}
                  td={showTwr ? undefined : 'line-through'}
                  style={{ cursor: 'pointer' }}
                >
                  TWR: {formatPct(lastTwr)}
                </Text>
              </UnstyledButton>
            )}
          </Group>
        </Group>
        <Text size="xs" c="dimmed" mb="sm">Guadagno assoluto e rendimento TWR combinati.</Text>
        <div style={{ height: 260 }}>
          {chartsLoading ? (
            <Group h="100%" justify="center">
              <Loader size="sm" />
              <Text c="dimmed" size="sm">Caricamento...</Text>
            </Group>
          ) : dualChartData.length === 0 ? (
            <Group h="100%" justify="center">
              <Text c="dimmed" size="sm">Nessun dato disponibile</Text>
            </Group>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={dualChartData}>
                <defs>
                  <linearGradient id="dualGainGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={gainChartColor} stopOpacity={0.18} />
                    <stop offset="95%" stopColor={gainChartColor} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="dualTwrGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={twrChartColor} stopOpacity={0.18} />
                    <stop offset="95%" stopColor={twrChartColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
                <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: tickColor, fontSize: 12 }} />
                <YAxis
                  yAxisId="gain"
                  orientation="left"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: tickColor, fontSize: 11 }}
                  width={55}
                  tickFormatter={(value: number) => formatNum(value, value >= 1000 ? 0 : 1)}
                  hide={!showGain}
                />
                <YAxis
                  yAxisId="twr"
                  orientation="right"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: tickColor, fontSize: 11 }}
                  width={45}
                  tickFormatter={(value: number) => `${formatNum(value, 1)}%`}
                  hide={!showTwr}
                />
                <RTooltip
                  content={({ active, payload, label }: any) => {
                    if (!active || !payload?.length) return null;
                    return (
                      <Paper withBorder p="xs" radius="sm" shadow="xs">
                        <Text size="xs" c="dimmed">{label}</Text>
                        {payload.map((entry: any) => {
                          const value = Number(entry.value ?? 0);
                          if (!Number.isFinite(value)) return null;
                          const isGain = entry.dataKey === 'gain';
                          return (
                            <Text key={entry.dataKey} size="sm" fw={600} c={getVariationColor(value)}>
                              {isGain ? `Guadagno: ${formatMoney(value, currency, true)}` : `TWR: ${formatPct(value)}`}
                            </Text>
                          );
                        })}
                      </Paper>
                    );
                  }}
                />
                {showGain && (
                  <Area
                    yAxisId="gain"
                    type="monotone"
                    dataKey="gain"
                    stroke={gainChartColor}
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#dualGainGrad)"
                    name="Guadagno"
                  />
                )}
                {showTwr && (
                  <Area
                    yAxisId="twr"
                    type="monotone"
                    dataKey="twr"
                    stroke={twrChartColor}
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#dualTwrGrad)"
                    name="TWR %"
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      <PerformanceChart
        title="Rendimento MWR (%)"
        data={mwrChartData}
        gradientId="mwrPerformanceGradient"
        color={mwrColor}
        stats={mwrStats}
        loading={chartsLoading}
        emptyMessage="Nessun dato MWR disponibile"
        subtitle="Money-Weighted Return ponderato sui flussi di cassa."
        tooltipContent={({ active, payload, label }: any) => {
          if (!active || !payload?.length) return null;
          const pct = Number(payload[0]?.value ?? 0);
          if (!Number.isFinite(pct)) return null;
          return (
            <Paper withBorder p="xs" radius="sm" shadow="xs">
              <Text size="xs" c="dimmed">{label}</Text>
              <Text size="sm" fw={600} c={getVariationColor(pct)}>{formatPct(pct)}</Text>
            </Paper>
          );
        }}
      />

      <Card withBorder radius="md" p="md" shadow="sm">
        <Group justify="space-between" align="center" mb="sm" wrap="wrap" gap="xs">
          <Text fw={600}>Heatmap rendimenti mensili</Text>
          {monthlyReturns && (
            <Text size="xs" c="dimmed">
              {formatShortDate(monthlyReturns.start_date)} - {formatShortDate(monthlyReturns.end_date)}
            </Text>
          )}
        </Group>
        {monthlyLoading ? (
          <Group justify="center" py="xl">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">Calcolo rendimenti mensili...</Text>
          </Group>
        ) : monthlyMatrix.length === 0 ? (
          <Text size="sm" c="dimmed">Nessun mese disponibile nel periodo selezionato.</Text>
        ) : (
          <Table
            withTableBorder={false}
            highlightOnHover={false}
            styles={{
              td: { padding: 6, borderBottom: 'none' },
              th: { padding: '0 6px 8px 6px', borderBottom: 'none' },
            }}
          >
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Anno</Table.Th>
                {MONTH_LABELS.map((month) => (
                  <Table.Th key={month} ta="center">{month}</Table.Th>
                ))}
                <Table.Th ta="center">YTD</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {monthlyMatrix.map((row) => (
                <Table.Tr key={row.year}>
                  <Table.Td>
                    <Text fw={700}>{row.year}</Text>
                  </Table.Td>
                  {MONTH_LABELS.map((_, index) => {
                    const value = row.months[index + 1] ?? null;
                    const colors = heatmapCellColors(value, isDark);
                    return (
                      <Table.Td key={`${row.year}-${index + 1}`} ta="center">
                        <div
                          style={{
                            minWidth: isMobile ? 58 : 64,
                            borderRadius: 10,
                            padding: '8px 6px',
                            background: colors.background,
                            color: colors.color,
                            border: colors.border,
                            fontSize: 12,
                            fontWeight: 700,
                          }}
                        >
                          {value == null ? '—' : formatPct(value)}
                        </div>
                      </Table.Td>
                    );
                  })}
                  <Table.Td ta="center">
                    <div
                      style={{
                        minWidth: isMobile ? 68 : 74,
                        borderRadius: 10,
                        padding: '8px 6px',
                        background: heatmapCellColors(row.yearReturn, isDark).background,
                        color: heatmapCellColors(row.yearReturn, isDark).color,
                        border: heatmapCellColors(row.yearReturn, isDark).border,
                        fontSize: 12,
                        fontWeight: 700,
                      }}
                    >
                      {row.yearReturn == null ? '—' : formatPct(row.yearReturn)}
                    </div>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Card>

      <Stack gap="md">
        <PerformanceChart
          title="Underwater drawdown"
          data={drawdownChartData}
          gradientId="drawdownGradient"
          color="#ef4444"
          loading={drawdownLoading}
          emptyMessage="Nessun drawdown disponibile"
          subtitle="Scostamento percentuale dal picco cumulato del periodo."
          stats={drawdown ? [
            { label: 'Max DD', value: formatPct(drawdown.max_drawdown_pct), color: getVariationColor(drawdown.max_drawdown_pct) },
            { label: 'Corrente', value: formatPct(drawdown.current_drawdown_pct), color: getVariationColor(drawdown.current_drawdown_pct) },
          ] : undefined}
          tooltipContent={({ active, payload, label }: any) => {
            if (!active || !payload?.length) return null;
            const value = Number(payload[0]?.value ?? 0);
            if (!Number.isFinite(value)) return null;
            return (
              <Paper withBorder p="xs" radius="sm" shadow="xs">
                <Text size="xs" c="dimmed">{label}</Text>
                <Text size="sm" fw={600} c={getVariationColor(value)}>{formatPct(value)}</Text>
              </Paper>
            );
          }}
        />

        {drawdown && (
          <SimpleGrid cols={{ base: 1, md: 3 }} spacing="sm">
            <Card withBorder radius="md" p="sm">
              <Text size="sm" c="dimmed">Picco storico nel range</Text>
              <Text fw={700}>
                {drawdown.peak_value != null ? formatMoney(drawdown.peak_value, currency) : 'N/D'}
              </Text>
              <Text size="xs" c="dimmed">{formatShortDate(drawdown.peak_date) ?? 'Data non disponibile'}</Text>
            </Card>
            <Card withBorder radius="md" p="sm">
              <Text size="sm" c="dimmed">Massimo drawdown</Text>
              <Text fw={700} c={getVariationColor(drawdown.max_drawdown_pct)}>
                {formatPct(drawdown.max_drawdown_pct)}
              </Text>
              <Text size="xs" c="dimmed">
                {formatShortDate(drawdown.max_drawdown_start) ?? 'N/D'} {'->'} {formatShortDate(drawdown.max_drawdown_end) ?? 'N/D'}
              </Text>
            </Card>
            <Card withBorder radius="md" p="sm">
              <Text size="sm" c="dimmed">Drawdown attuale</Text>
              <Text fw={700} c={getVariationColor(drawdown.current_drawdown_pct)}>
                {formatPct(drawdown.current_drawdown_pct)}
              </Text>
              <Text size="xs" c="dimmed">Dal picco più recente del periodo selezionato</Text>
            </Card>
          </SimpleGrid>
        )}
      </Stack>

      <Stack gap="md">
        <Group justify="space-between" align="center" wrap="wrap" gap="xs">
          <Text fw={600}>Rolling windows</Text>
          <SegmentedControl
            size="xs"
            value={rollingWindow}
            onChange={(value) => setRollingWindow((value as RollingWindowKey) ?? '12')}
            data={ROLLING_WINDOW_OPTIONS}
          />
        </Group>

        <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
          <PerformanceChart
            title={`CAGR rolling ${rollingWindow}M`}
            data={rollingCagrData}
            gradientId="rollingCagrGradient"
            color="#2563eb"
            loading={rollingLoading}
            emptyMessage={`Servono almeno ${rollingWindow} mesi di storico`}
            subtitle="Rendimento annualizzato della finestra mobile."
            stats={rollingLatest?.cagr_pct != null ? [
              { label: 'Ultimo', value: formatPct(rollingLatest.cagr_pct), color: getVariationColor(rollingLatest.cagr_pct) },
            ] : undefined}
            tooltipContent={({ active, payload, label }: any) => {
              if (!active || !payload?.length) return null;
              const value = Number(payload[0]?.value ?? 0);
              if (!Number.isFinite(value)) return null;
              return (
                <Paper withBorder p="xs" radius="sm" shadow="xs">
                  <Text size="xs" c="dimmed">{label}</Text>
                  <Text size="sm" fw={600} c={getVariationColor(value)}>{formatPct(value)}</Text>
                </Paper>
              );
            }}
          />

          <PerformanceChart
            title={`Volatilità rolling ${rollingWindow}M`}
            data={rollingVolData}
            gradientId="rollingVolGradient"
            color="#f59e0b"
            loading={rollingLoading}
            emptyMessage={`Servono almeno ${rollingWindow} mesi di storico`}
            subtitle="Deviazione standard annualizzata dei rendimenti mensili."
            stats={rollingLatest?.volatility_pct != null ? [
              { label: 'Ultima', value: formatPctPlain(rollingLatest.volatility_pct), color: 'yellow' },
            ] : undefined}
            tooltipContent={({ active, payload, label }: any) => {
              if (!active || !payload?.length) return null;
              const value = Number(payload[0]?.value ?? 0);
              if (!Number.isFinite(value)) return null;
              return (
                <Paper withBorder p="xs" radius="sm" shadow="xs">
                  <Text size="xs" c="dimmed">{label}</Text>
                  <Text size="sm" fw={600}>{formatPctPlain(value)}</Text>
                </Paper>
              );
            }}
          />

          <PerformanceChart
            title={`Sharpe rolling ${rollingWindow}M`}
            data={rollingSharpeData}
            gradientId="rollingSharpeGradient"
            color="#7c3aed"
            loading={rollingLoading}
            emptyMessage={`Servono almeno ${rollingWindow} mesi di storico`}
            subtitle="Sharpe ratio con risk-free al 2%."
            stats={rollingLatest?.sharpe_ratio != null ? [
              { label: 'Ultimo', value: formatNum(rollingLatest.sharpe_ratio, 2), color: rollingLatest.sharpe_ratio >= 0 ? 'grape' : 'red' },
            ] : undefined}
            tooltipContent={({ active, payload, label }: any) => {
              if (!active || !payload?.length) return null;
              const value = Number(payload[0]?.value ?? 0);
              if (!Number.isFinite(value)) return null;
              return (
                <Paper withBorder p="xs" radius="sm" shadow="xs">
                  <Text size="xs" c="dimmed">{label}</Text>
                  <Text size="sm" fw={600} c={getVariationColor(value)}>{formatNum(value, 2)}</Text>
                </Paper>
              );
            }}
          />
        </SimpleGrid>
      </Stack>

      <Card withBorder radius="md" p="md" shadow="sm">
        <Group justify="space-between" align="center" mb="sm" wrap="wrap" gap="xs">
          <Text fw={600}>Hall of Fame</Text>
          {hallLoading && (
            <Group gap="xs">
              <Loader size="sm" />
              <Text size="sm" c="dimmed">Caricamento classifiche...</Text>
            </Group>
          )}
        </Group>
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
          <RankedListCard title="Mesi migliori" items={hallOfFame?.best_months ?? []} />
          <RankedListCard title="Mesi peggiori" items={hallOfFame?.worst_months ?? []} />
          <RankedListCard title="Anni migliori" items={hallOfFame?.best_years ?? []} />
          <RankedListCard title="Anni peggiori" items={hallOfFame?.worst_years ?? []} />
        </SimpleGrid>
      </Card>
    </Stack>
  );
}
