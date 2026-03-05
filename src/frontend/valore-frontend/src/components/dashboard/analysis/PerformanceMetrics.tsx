import { useMemo, useState } from 'react';
import { Alert, Card, Group, Loader, Paper, SegmentedControl, SimpleGrid, Stack, Text, Tooltip } from '@mantine/core';
import { usePerformanceSummary, useTWRTimeseries, useGainTimeseries, useMWRTimeseries } from '../hooks/queries';
import { formatMoney, formatPct, getVariationColor } from '../formatters';
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

export function PerformanceMetrics({ portfolioId }: PerformanceMetricsProps) {
  const [period, setPeriod] = useState<PeriodKey>('1y');
  const startDate = periodToStartDate(period);

  const { data: summary, isLoading: summaryLoading, error: summaryError } = usePerformanceSummary(portfolioId, period);
  const { data: twrPoints = [], isLoading: twrLoading } = useTWRTimeseries(portfolioId, startDate);
  const { data: gainPoints = [], isLoading: gainLoading } = useGainTimeseries(portfolioId, startDate);
  const { data: mwrPoints = [], isLoading: mwrLoading } = useMWRTimeseries(portfolioId, startDate);

  const loading = summaryLoading;
  const chartsLoading = twrLoading || gainLoading || mwrLoading;
  const error = summaryError instanceof Error ? summaryError.message : null;

  const currency = 'EUR';

  const twrChartData = useMemo(
    () => twrPoints.map((p) => ({
      rawDate: p.date,
      date: formatChartDate(p.date),
      value: p.cumulative_twr_pct,
    })),
    [twrPoints],
  );

  const twrStats = useMemo(() => {
    if (!twrPoints.length) return undefined;
    const last = twrPoints[twrPoints.length - 1].cumulative_twr_pct;
    return [{ label: 'TWR', value: formatPct(last), color: getVariationColor(last) }];
  }, [twrPoints]);

  const twrColor = useMemo(() => {
    if (!twrPoints.length) return '#228be6';
    const last = twrPoints[twrPoints.length - 1].cumulative_twr_pct;
    return last >= 0 ? '#16a34a' : '#dc2626';
  }, [twrPoints]);

  const gainChartData = useMemo(
    () => gainPoints.map((p) => ({
      rawDate: p.date,
      date: formatChartDate(p.date),
      value: p.absolute_gain,
    })),
    [gainPoints],
  );

  const gainStats = useMemo(() => {
    if (!gainPoints.length) return undefined;
    const last = gainPoints[gainPoints.length - 1].absolute_gain;
    return [{ label: '', value: formatMoney(last, currency, true), color: getVariationColor(last) }];
  }, [gainPoints, currency]);

  const gainColor = useMemo(() => {
    if (!gainPoints.length) return '#228be6';
    const last = gainPoints[gainPoints.length - 1].absolute_gain;
    return last >= 0 ? '#16a34a' : '#dc2626';
  }, [gainPoints]);

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
            <Text fw={700}>{summary ? formatMoney(summary.net_invested, currency) : 'N/D'}</Text>
          </Card>

          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Versato</Text>
            <Text fw={700}>{summary ? formatMoney(summary.total_deposits, currency) : 'N/D'}</Text>
          </Card>

          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Prelevato</Text>
            <Text fw={700}>{summary ? formatMoney(summary.total_withdrawals, currency) : 'N/D'}</Text>
          </Card>

          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Guadagno Assoluto</Text>
            <Text fw={700} style={{ color: kpiColor(summary?.absolute_gain) }}>
              {summary ? formatMoney(summary.absolute_gain, currency) : 'N/D'}
            </Text>
          </Card>

          <Card withBorder radius="md" p="sm">
            <Tooltip label="Time-Weighted Return — rendimento del portafoglio al netto dei flussi di cassa" multiline w={280} withArrow>
              <Text size="sm" c="dimmed" style={{ cursor: 'help' }}>TWR</Text>
            </Tooltip>
            <Text fw={700} style={{ color: kpiColor(summary?.twr?.twr_pct) }}>
              {summary?.twr?.twr_pct != null ? formatPct(summary.twr.twr_pct) : 'N/D'}
            </Text>
          </Card>

          <Card withBorder radius="md" p="sm">
            <Tooltip label="Money-Weighted Return — rendimento ponderato per i flussi di cassa dell'investitore" multiline w={280} withArrow>
              <Text size="sm" c="dimmed" style={{ cursor: 'help' }}>MWR</Text>
            </Tooltip>
            <Text fw={700} style={{ color: kpiColor(summary?.mwr?.mwr_pct) }}>
              {summary?.mwr?.mwr_pct != null ? formatPct(summary.mwr.mwr_pct) : 'N/D'}
            </Text>
          </Card>
        </SimpleGrid>
      </Card>

      <PerformanceChart
        title="Guadagno Assoluto"
        data={gainChartData}
        gradientId="gainPerformanceGradient"
        color={gainColor}
        stats={gainStats}
        loading={chartsLoading}
        emptyMessage="Nessun dato di guadagno disponibile"
        subtitle="Valore portafoglio meno netto investito (depositi - prelievi)"
        tooltipContent={({ active, payload, label }: any) => {
          if (!active || !payload?.length) return null;
          const gain = Number(payload[0]?.value ?? 0);
          if (!Number.isFinite(gain)) return null;
          const point = gainPoints.find((p) => formatChartDate(p.date) === label);
          return (
            <Paper withBorder p="xs" radius="sm" shadow="xs">
              <Text size="xs" c="dimmed">{label}</Text>
              <Text size="sm" fw={600} c={getVariationColor(gain)}>
                {formatMoney(gain, currency, true)}
              </Text>
              {point && (
                <>
                  <Text size="xs" c="dimmed">Valore: {formatMoney(point.portfolio_value, currency)}</Text>
                  <Text size="xs" c="dimmed">Investito: {formatMoney(point.net_invested, currency)}</Text>
                </>
              )}
            </Paper>
          );
        }}
      />

      <PerformanceChart
        title="Rendimento TWR (%)"
        data={twrChartData}
        gradientId="twrPerformanceGradient"
        color={twrColor}
        stats={twrStats}
        loading={chartsLoading}
        emptyMessage="Nessun dato di rendimento disponibile"
        subtitle="Time-Weighted Return — rendimento del portafoglio al netto dei flussi di cassa"
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
