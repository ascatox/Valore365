import { useMemo, useState } from 'react';
import { Paper, Stack, Text } from '@mantine/core';
import {
  useGainTimeseries,
  useHallOfFame,
  useMonthlyReturns,
  useMWRTimeseries,
  usePerformanceSummary,
  usePortfolioDrawdown,
  usePortfolioSummary,
  useRollingWindows,
  useTWRTimeseries,
} from '../hooks/queries';
import { formatPct, getVariationColor } from '../formatters';
import { PerformanceChart } from '../summary/PerformanceChart';
import { PerformanceKpiSummary } from '../performance/PerformanceKpiSummary';
import { GainTwrChart } from '../performance/GainTwrChart';
import { MonthlyReturnsHeatmap } from '../performance/MonthlyReturnsHeatmap';
import { DrawdownSection } from '../performance/DrawdownSection';
import { RollingWindowsSection } from '../performance/RollingWindowsSection';
import { HallOfFameSection } from '../performance/HallOfFameSection';
import { formatChartDate, formatYearMonth, periodToStartDate } from '../performance/utils';
import type { PeriodKey, RollingWindowKey } from '../performance/utils';

interface PerformanceMetricsProps {
  portfolioId: number | null;
}

export function PerformanceMetrics({ portfolioId }: PerformanceMetricsProps) {
  const [period, setPeriod] = useState<PeriodKey>('1y');
  const [rollingWindow, setRollingWindow] = useState<RollingWindowKey>('12');
  const startDate = periodToStartDate(period);

  const { data: portfolioSummary } = usePortfolioSummary(portfolioId);
  const { data: summary, isLoading: summaryLoading, error: summaryError } = usePerformanceSummary(portfolioId, period);
  const { data: twrPoints = [], isLoading: twrLoading } = useTWRTimeseries(portfolioId, startDate);
  const { data: gainPoints = [], isLoading: gainLoading } = useGainTimeseries(portfolioId, startDate);
  const { data: mwrPoints = [], isLoading: mwrLoading } = useMWRTimeseries(portfolioId, startDate);
  const { data: monthlyReturns, isLoading: monthlyLoading } = useMonthlyReturns(portfolioId, startDate);
  const { data: drawdown, isLoading: drawdownLoading } = usePortfolioDrawdown(portfolioId, startDate);
  const { data: rolling, isLoading: rollingLoading } = useRollingWindows(portfolioId, Number(rollingWindow), 2, startDate);
  const { data: hallOfFame, isLoading: hallLoading } = useHallOfFame(portfolioId, 5, startDate);

  const chartsLoading = twrLoading || gainLoading || mwrLoading;
  const error = summaryError instanceof Error ? summaryError.message : null;
  const currency = portfolioSummary?.base_currency ?? 'EUR';

  const dualChartData = useMemo(() => {
    const dateMap = new Map<string, { date: string; gain?: number; twr?: number }>();
    for (const p of gainPoints) {
      const entry = dateMap.get(p.date) ?? { date: formatChartDate(p.date) };
      entry.gain = p.absolute_gain;
      dateMap.set(p.date, entry);
    }
    for (const p of twrPoints) {
      const entry = dateMap.get(p.date) ?? { date: formatChartDate(p.date) };
      entry.twr = p.cumulative_twr_pct;
      dateMap.set(p.date, entry);
    }
    return Array.from(dateMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([, value]) => value);
  }, [gainPoints, twrPoints]);

  const lastGain = gainPoints.length ? gainPoints[gainPoints.length - 1].absolute_gain : null;
  const lastTwr = twrPoints.length ? twrPoints[twrPoints.length - 1].cumulative_twr_pct : null;

  const mwrChartData = useMemo(
    () => mwrPoints
      .filter((p) => p.cumulative_mwr_pct != null)
      .map((p) => ({ rawDate: p.date, date: formatChartDate(p.date), value: p.cumulative_mwr_pct as number })),
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
      .map(([year, months]) => ({ year, months, yearReturn: yearlyMap.get(year) ?? null }));
  }, [monthlyReturns]);

  const drawdownChartData = useMemo(
    () => (drawdown?.points ?? []).map((point) => ({
      rawDate: point.date, date: formatChartDate(point.date), value: point.drawdown_pct,
    })),
    [drawdown],
  );

  const rollingCagrData = useMemo(
    () => (rolling?.points ?? []).filter((p) => p.cagr_pct != null)
      .map((p) => ({ rawDate: p.date, date: formatYearMonth(p.date), value: p.cagr_pct as number })),
    [rolling],
  );

  const rollingVolData = useMemo(
    () => (rolling?.points ?? []).filter((p) => p.volatility_pct != null)
      .map((p) => ({ rawDate: p.date, date: formatYearMonth(p.date), value: p.volatility_pct as number })),
    [rolling],
  );

  const rollingSharpeData = useMemo(
    () => (rolling?.points ?? []).filter((p) => p.sharpe_ratio != null)
      .map((p) => ({ rawDate: p.date, date: formatYearMonth(p.date), value: p.sharpe_ratio as number })),
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
    return mwrChartData[mwrChartData.length - 1].value >= 0 ? '#16a34a' : '#dc2626';
  }, [mwrChartData]);

  return (
    <Stack gap="md">
      <PerformanceKpiSummary
        summary={summary}
        loading={summaryLoading}
        error={error}
        currency={currency}
        period={period}
        onPeriodChange={setPeriod}
      />

      <GainTwrChart
        data={dualChartData}
        loading={chartsLoading}
        currency={currency}
        lastGain={lastGain}
        lastTwr={lastTwr}
      />

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

      <MonthlyReturnsHeatmap
        matrix={monthlyMatrix}
        loading={monthlyLoading}
        startDate={monthlyReturns?.start_date}
        endDate={monthlyReturns?.end_date}
      />

      <DrawdownSection
        drawdown={drawdown}
        chartData={drawdownChartData}
        loading={drawdownLoading}
        currency={currency}
      />

      <RollingWindowsSection
        rollingWindow={rollingWindow}
        onRollingWindowChange={setRollingWindow}
        cagrData={rollingCagrData}
        volData={rollingVolData}
        sharpeData={rollingSharpeData}
        latest={rollingLatest}
        loading={rollingLoading}
      />

      <HallOfFameSection hallOfFame={hallOfFame} loading={hallLoading} />
    </Stack>
  );
}
