import { useMemo, useState } from 'react';
import { Card, Grid, Paper, SegmentedControl, Text } from '@mantine/core';
import { AnalysisKpiGrid } from '../analysis/AnalysisKpiGrid';
import { PerformanceMetrics } from '../analysis/PerformanceMetrics';
import { PerformanceChart } from '../summary/PerformanceChart';
import { AssetMiniChartsGrid } from '../analysis/AssetMiniChartsGrid';
import { AllocationDoughnut } from '../summary/AllocationDoughnut';
import { PerformersTable } from '../analysis/PerformersTable';
import { IntradayModal } from '../analysis/IntradayModal';
import { DASHBOARD_WINDOWS } from '../constants';
import { formatNum, formatPct, getVariationColor } from '../formatters';
import {
  useTargetAllocation,
  useTargetPerformance,
  useTargetAssetPerformance,
  usePortfolioSummary,
  usePortfolioTimeseries,
  useIntradayTargetPerformance,
  useAssetIntradayTargetPerformance,
  useIntradayDetail,
  usePortfolios,
} from '../hooks/queries';
import type { AllocationDoughnutItem, ChartPoint, IntradayChartPoint, PerformerItem } from '../types';
import { ENABLE_TARGET_ALLOCATION } from '../../../features';

interface AnalisiTabProps {
  portfolioId: number | null;
  chartWindow: string;
  setChartWindow: (w: string) => void;
}

export function AnalisiTab({ portfolioId, chartWindow, setChartWindow }: AnalisiTabProps) {
  const [intradayOpen, setIntradayOpen] = useState(false);
  const [intradayDate, setIntradayDate] = useState<string | null>(null);
  const [intradayDateLabel, setIntradayDateLabel] = useState<string | null>(null);

  // --- Queries ---
  const { data: portfolios = [] } = usePortfolios();
  const { data: allocation = [] } = useTargetAllocation(portfolioId);
  const { data: targetPerformance } = useTargetPerformance(portfolioId);
  const { data: assetPerformance } = useTargetAssetPerformance(portfolioId);
  const { data: portfolioSummary } = usePortfolioSummary(portfolioId);
  const { data: portfolioTimeseries = [] } = usePortfolioTimeseries(portfolioId);

  const isIntraday = chartWindow === '1';
  const chartWindowDays = useMemo(
    () => DASHBOARD_WINDOWS.find((w) => w.value === chartWindow)?.days ?? 90,
    [chartWindow],
  );

  const { data: mainIntradayData, isLoading: mainIntradayLoading } = useIntradayTargetPerformance(portfolioId, isIntraday);
  const { data: assetIntradayPerformance, isLoading: assetIntradayLoading } = useAssetIntradayTargetPerformance(portfolioId, isIntraday);
  const { data: intradayDetailData, isLoading: intradayLoading, error: intradayError } = useIntradayDetail(portfolioId, intradayDate);

  const selectedPortfolio = useMemo(
    () => portfolios.find((p) => p.id === portfolioId) ?? null,
    [portfolios, portfolioId],
  );

  const mvpCurrency = portfolioSummary?.base_currency ?? selectedPortfolio?.base_currency ?? 'EUR';
  const totalAssignedWeight = allocation.reduce((sum, item) => sum + item.weight_pct, 0);

  // --- Computed chart data ---
  const chartData = useMemo<ChartPoint[]>(() => {
    if (ENABLE_TARGET_ALLOCATION) {
      return (targetPerformance?.points ?? [])
        .filter((point) => point.weighted_index > 0)
        .slice(-chartWindowDays)
        .map((point) => ({
          rawDate: point.date,
          date: new Date(point.date).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }),
          value: point.weighted_index,
        }));
    }
    const points = portfolioTimeseries
      .filter((point) => Number.isFinite(point.market_value) && point.market_value > 0)
      .slice(-chartWindowDays);
    const base = points[0]?.market_value ?? 0;
    if (!Number.isFinite(base) || base <= 0) return [];
    return points.map((point) => ({
      rawDate: point.date,
      date: new Date(point.date).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }),
      value: (point.market_value / base) * 100,
    }));
  }, [targetPerformance, chartWindowDays, portfolioTimeseries]);

  const mainIntradayChartData = useMemo<IntradayChartPoint[]>(
    () =>
      (mainIntradayData?.points ?? []).map((p) => ({
        ts: p.ts,
        time: new Date(p.ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
        value: p.weighted_index,
      })),
    [mainIntradayData],
  );

  const indexCardStats = useMemo(() => {
    if (isIntraday) {
      const values = (mainIntradayData?.points ?? []).map((p) => p.weighted_index).filter((v) => Number.isFinite(v));
      if (!values.length || values[0] <= 0) return null;
      const last = values[values.length - 1];
      return { index: last, diffPts: last - 100, diffPct: ((last / values[0]) - 1) * 100 };
    }
    const values = chartData.map((p) => p.value).filter((v) => Number.isFinite(v));
    if (!values.length || values[0] <= 0) return null;
    const last = values[values.length - 1];
    return { index: last, diffPts: last - 100, diffPct: ((last / values[0]) - 1) * 100 };
  }, [isIntraday, chartData, mainIntradayData]);

  const mainChartStats = useMemo(() => {
    const series = isIntraday ? mainIntradayChartData : chartData;
    if (!series.length) return null;
    const first = Number(series[0]?.value ?? 0);
    const last = Number(series[series.length - 1]?.value ?? 0);
    if (!Number.isFinite(first) || !Number.isFinite(last) || first <= 0) return null;
    return { last, periodPct: ((last / first) - 1) * 100 };
  }, [isIntraday, mainIntradayChartData, chartData]);

  const assetMiniCharts = useMemo(() => {
    if (isIntraday) {
      return (assetIntradayPerformance?.assets ?? []).map((asset) => ({
        ...asset,
        chart: asset.points.map((p) => ({
          rawDate: p.ts,
          time: new Date(p.ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
          value: p.weighted_index,
        })),
      }));
    }
    const visibleDates = new Set(chartData.map((p) => p.rawDate));
    return (assetPerformance?.assets ?? []).map((asset) => ({
      ...asset,
      chart: asset.points
        .filter((p) => visibleDates.has(p.date))
        .map((p) => ({
          rawDate: p.date,
          date: new Date(p.date).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }),
          value: p.index_value,
        })),
    }));
  }, [isIntraday, assetIntradayPerformance, assetPerformance, chartData]);

  const targetAllocationData = useMemo<AllocationDoughnutItem[]>(
    () => allocation.map((item) => ({ name: item.symbol, value: item.weight_pct, asset_id: item.asset_id })),
    [allocation],
  );

  const performerStats = useMemo(() => {
    const computed = assetMiniCharts
      .map((asset) => {
        const values = asset.chart.map((p) => Number(p.value)).filter((v) => Number.isFinite(v));
        if (values.length < 2) return null;
        const first = values[0];
        const last = values[values.length - 1];
        if (!Number.isFinite(first) || !Number.isFinite(last) || first <= 0) return null;
        const returnPct = ((last / first) - 1) * 100;
        return {
          symbol: asset.symbol,
          name: asset.name,
          return_pct: returnPct,
          as_of: asset.as_of,
          asset_id: asset.asset_id,
        } satisfies PerformerItem;
      })
      .filter(Boolean) as PerformerItem[];

    if (!computed.length) {
      return { best: null as PerformerItem | null, worst: null as PerformerItem | null, rows: [] as PerformerItem[] };
    }

    const sorted = [...computed].sort((a, b) => b.return_pct - a.return_pct);
    const best = sorted[0] ?? null;
    const worst = sorted[sorted.length - 1] ?? null;
    const rows = best && worst && best.asset_id !== worst.asset_id ? [best, worst] : best ? [best] : [];
    return { best, worst, rows };
  }, [assetMiniCharts]);

  // --- Intraday modal ---
  const intradayChartData = useMemo<IntradayChartPoint[]>(
    () =>
      (intradayDetailData?.points ?? []).map((p) => ({
        ts: p.ts,
        time: new Date(p.ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
        value: p.weighted_index,
      })),
    [intradayDetailData],
  );

  const intradayStats = useMemo(() => {
    if (!intradayChartData.length) return null;
    const values = intradayChartData.map((p) => p.value).filter((v) => Number.isFinite(v));
    if (!values.length) return null;
    const open = values[0];
    const last = values[values.length - 1];
    const min = Math.min(...values);
    const max = Math.max(...values);
    const dayPct = open > 0 ? ((last / open) - 1) * 100 : 0;
    return { open, last, min, max, dayPct };
  }, [intradayChartData]);

  const handleDailyChartClick = (state: any) => {
    if (!ENABLE_TARGET_ALLOCATION) return;
    const payload = state?.activePayload?.[0]?.payload;
    const rawDate = payload?.rawDate as string | undefined;
    if (!rawDate || !portfolioId) return;
    setIntradayDate(rawDate);
    setIntradayDateLabel(new Date(rawDate).toLocaleDateString('it-IT'));
    setIntradayOpen(true);
  };

  const activeChartData = isIntraday ? mainIntradayChartData : chartData;
  const chartXKey = isIntraday ? 'time' : 'date';

  const chartStats = mainChartStats
    ? [
        { label: 'Indice', value: formatNum(mainChartStats.last), color: 'blue' },
        { label: 'Var', value: formatPct(mainChartStats.periodPct), color: getVariationColor(mainChartStats.periodPct) },
      ]
    : undefined;

  const renderIndexTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const rawValue = Number(payload[0]?.value ?? 0);
    if (!Number.isFinite(rawValue)) return null;
    const pct = ((rawValue / 100) - 1) * 100;
    return (
      <Paper withBorder p="xs" radius="sm" shadow="xs">
        <Text size="xs" c="dimmed">{isIntraday ? `Ora ${label}` : `Data ${label}`}</Text>
        <Text size="sm" fw={600}>Indice: {formatNum(rawValue)}</Text>
        <Text size="sm" c={getVariationColor(pct)} fw={500}>Variazione: {formatPct(pct)}</Text>
      </Paper>
    );
  };

  return (
    <>
      <PerformanceMetrics portfolioId={portfolioId} />

      <AnalysisKpiGrid
        indexCardStats={indexCardStats}
        totalAssignedWeight={totalAssignedWeight}
        allocation={allocation}
        selectedPortfolio={selectedPortfolio}
        portfolioSummary={portfolioSummary ?? null}
        currency={mvpCurrency}
        bestPerformer={performerStats.best}
        worstPerformer={performerStats.worst}
      />

      <div style={{ marginTop: 16 }}>
        <PerformanceChart
          title="Indice Target (media pesata, base 100)"
          data={activeChartData}
          xKey={chartXKey}
          gradientId={isIntraday ? 'colorValueIntradayMain' : 'colorValue'}
          color="#228be6"
          height={300}
          loading={isIntraday ? mainIntradayLoading : false}
          emptyMessage={isIntraday ? 'Nessun dato intraday disponibile per oggi' : 'Nessun dato storico disponibile'}
          onClick={!isIntraday ? handleDailyChartClick : undefined}
          stats={chartStats}
          tooltipContent={renderIndexTooltip}
          headerRight={
            <SegmentedControl
              size="xs"
              value={chartWindow}
              onChange={setChartWindow}
              data={DASHBOARD_WINDOWS.map((w) => ({ label: w.label, value: w.value }))}
            />
          }
        />
      </div>

      <Card withBorder radius="md" p="md" mt="md" shadow="sm">
        <Text fw={500} mb="md">
          Andamento per Titolo ({chartWindowDays === 1 ? 'oggi' : `ultimi ${chartWindowDays} giorni`})
        </Text>
        <AssetMiniChartsGrid
          assets={assetMiniCharts}
          chartWindow={chartWindow}
          assetIntradayLoading={assetIntradayLoading}
        />
      </Card>

      <Grid gutter="md" mt="md">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <AllocationDoughnut
            title="Allocazione Target"
            data={targetAllocationData}
            centerLabel={totalAssignedWeight > 0 ? `${Math.round(totalAssignedWeight)}%` : '0%'}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card withBorder radius="md" p={0} shadow="sm">
            <PerformersTable performers={performerStats.rows} />
          </Card>
        </Grid.Col>
      </Grid>

      <IntradayModal
        opened={intradayOpen}
        onClose={() => { setIntradayOpen(false); setIntradayDate(null); }}
        dateLabel={intradayDateLabel}
        loading={intradayLoading}
        error={intradayError instanceof Error ? intradayError.message : intradayError ? String(intradayError) : null}
        chartData={intradayChartData}
        stats={intradayStats}
      />
    </>
  );
}
