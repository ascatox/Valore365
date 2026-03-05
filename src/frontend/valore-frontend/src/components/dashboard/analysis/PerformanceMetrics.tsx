import { useMemo, useState } from 'react';
import { Alert, Card, Group, Loader, Paper, SegmentedControl, SimpleGrid, Stack, Text, Tooltip, UnstyledButton } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer, Legend } from 'recharts';
import { usePerformanceSummary, useTWRTimeseries, useGainTimeseries, useMWRTimeseries } from '../hooks/queries';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../formatters';
import { PerformanceChart } from '../summary/PerformanceChart';

type PeriodKey = '1m' | '3m' | '6m' | 'ytd' | '1y' | '3y' | 'all';

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

function NdTooltip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Tooltip label={label} multiline w={280} withArrow>
      <Text fw={700} style={{ cursor: 'help' }}>{children}</Text>
    </Tooltip>
  );
}

export function PerformanceMetrics({ portfolioId }: PerformanceMetricsProps) {
  const [period, setPeriod] = useState<PeriodKey>('1y');
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

  const loading = summaryLoading;
  const chartsLoading = twrLoading || gainLoading || mwrLoading;
  const error = summaryError instanceof Error ? summaryError.message : null;

  const currency = 'EUR';

  // Dual-axis chart data: merge gain and TWR by date
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
      .map(([, v]) => v);
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

      {/* Consolidated Gain + TWR dual-axis chart */}
      <Card withBorder radius="md" p="md" shadow="sm">
        <Group justify="space-between" mb="xs" align="center" wrap="wrap" gap="xs">
          <Group gap="xs">
            <Text fw={600} size="sm">Guadagno & TWR</Text>
            {lastGain != null && (
              <UnstyledButton onClick={() => setShowGain((v) => !v)}>
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
              <UnstyledButton onClick={() => setShowTwr((v) => !v)}>
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
        <Text size="xs" c="dimmed" mb="sm">Guadagno assoluto e rendimento TWR combinati — clicca sulla legenda per mostrare/nascondere</Text>
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
                  tickFormatter={(v: number) => formatNum(v, v >= 1000 ? 0 : 1)}
                  hide={!showGain}
                />
                <YAxis
                  yAxisId="twr"
                  orientation="right"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: tickColor, fontSize: 11 }}
                  width={45}
                  tickFormatter={(v: number) => `${formatNum(v, 1)}%`}
                  hide={!showTwr}
                />
                <RTooltip
                  content={({ active, payload, label }: any) => {
                    if (!active || !payload?.length) return null;
                    return (
                      <Paper withBorder p="xs" radius="sm" shadow="xs">
                        <Text size="xs" c="dimmed">{label}</Text>
                        {payload.map((entry: any) => {
                          const val = Number(entry.value ?? 0);
                          if (!Number.isFinite(val)) return null;
                          const isGain = entry.dataKey === 'gain';
                          return (
                            <Text key={entry.dataKey} size="sm" fw={600} c={getVariationColor(val)}>
                              {isGain ? `Guadagno: ${formatMoney(val, currency, true)}` : `TWR: ${formatPct(val)}`}
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
        subtitle="Money-Weighted Return — rendimento ponderato per i flussi di cassa dell'investitore"
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
    </Stack>
  );
}
