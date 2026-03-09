import { useMemo, useState } from 'react';
import { Alert, Badge, Card, Grid, Group, Loader, Paper, SegmentedControl, Select, Text } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { IconAlertTriangle, IconCoin, IconActivity, IconArrowUpRight } from '@tabler/icons-react';
import { KpiStatsGrid } from '../summary/KpiStatsGrid';
import { PerformanceChart } from '../summary/PerformanceChart';
import { AllocationDoughnut } from '../summary/AllocationDoughnut';
import { BestWorstCards } from '../summary/BestWorstCards';
import { DashboardMobileKpiCarousel } from '../../mobile/DashboardMobileKpiCarousel';
import { DASHBOARD_WINDOWS } from '../constants';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../formatters';
import {
  usePortfolioSummary,
  usePortfolioPositions,
  usePortfolioAllocation,
  usePortfolioTimeseries,
  usePortfolioIntradayTimeseries,
  usePortfolioDataCoverage,
  useGainTimeseries,
  useBenchmarks,
  useBenchmarkPrices,
} from '../hooks/queries';
import type { PerformerItem, AllocationDoughnutItem } from '../types';

interface PanoramicaTabProps {
  portfolioId: number | null;
  chartWindow: string;
  setChartWindow: (w: string) => void;
}

export function PanoramicaTab({ portfolioId, chartWindow, setChartWindow }: PanoramicaTabProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const gridColor = isDark ? theme.colors.dark[4] : '#e9ecef';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  const [selectedBenchmarkId, setSelectedBenchmarkId] = useState<number | null>(null);
  const [staleAlertDismissed, setStaleAlertDismissed] = useState(false);

  // --- Queries ---
  const { data: portfolioSummary } = usePortfolioSummary(portfolioId);
  const { data: portfolioPositions = [] } = usePortfolioPositions(portfolioId);
  const { data: portfolioAllocationData = [] } = usePortfolioAllocation(portfolioId);
  const { data: portfolioTimeseries = [] } = usePortfolioTimeseries(portfolioId);
  const { data: dataCoverage } = usePortfolioDataCoverage(portfolioId);
  const { data: benchmarkList = [] } = useBenchmarks();

  const isIntradayWindow = chartWindow === '1';
  const chartWindowDays = useMemo(
    () => DASHBOARD_WINDOWS.find((w) => w.value === chartWindow)?.days ?? 90,
    [chartWindow],
  );

  const gainStartDate = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - chartWindowDays);
    return d.toISOString().slice(0, 10);
  }, [chartWindowDays]);

  const benchmarkStartDate = gainStartDate;

  const { data: portfolioIntradayRaw = [], isLoading: _intradayLoading } = usePortfolioIntradayTimeseries(portfolioId, isIntradayWindow);
  const { data: gainPoints = [], isLoading: gainChartLoading } = useGainTimeseries(portfolioId, gainStartDate);
  const { data: benchmarkPrices = [], isLoading: benchmarkLoading } = useBenchmarkPrices(selectedBenchmarkId, portfolioId, benchmarkStartDate);

  // --- Computed values ---
  const mvpCurrency = portfolioSummary?.base_currency ?? 'EUR';

  const mvpTimeseriesData = useMemo(
    () =>
      portfolioTimeseries
        .filter((point) => Number.isFinite(point.market_value) && point.market_value > 0)
        .slice(-(isIntradayWindow ? 2 : chartWindowDays))
        .map((point) => ({
          rawDate: point.date,
          date: new Date(point.date).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }),
          value: point.market_value,
        })),
    [portfolioTimeseries, isIntradayWindow, chartWindowDays],
  );

  const portfolioIntradayData = useMemo(
    () =>
      portfolioIntradayRaw
        .filter((p) => Number.isFinite(p.market_value) && p.market_value > 0)
        .map((p) => ({
          ts: p.ts,
          time: new Date(p.ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
          value: p.market_value,
        })),
    [portfolioIntradayRaw],
  );

  const mvpTimeseriesStats = useMemo(() => {
    if (!mvpTimeseriesData.length) return null;
    const first = Number(mvpTimeseriesData[0]?.value ?? 0);
    const last = Number(mvpTimeseriesData[mvpTimeseriesData.length - 1]?.value ?? 0);
    if (!Number.isFinite(last)) return null;
    if (!Number.isFinite(first) || first <= 0) return { last, pct: 0 };
    return { last, pct: ((last / first) - 1) * 100 };
  }, [mvpTimeseriesData]);

  const portfolioChartData = isIntradayWindow && portfolioIntradayData.length > 0
    ? portfolioIntradayData
    : mvpTimeseriesData;

  const portfolioChartStats = useMemo(() => {
    const series = portfolioChartData;
    if (!series.length) return undefined;
    const last = Number(series[series.length - 1]?.value ?? 0);
    if (!Number.isFinite(last)) return undefined;
    if (isIntradayWindow && portfolioSummary) {
      const pct = portfolioSummary.day_change_pct;
      return [
        { label: '', value: formatMoney(last, mvpCurrency), color: 'blue' },
        { label: 'Var', value: formatPct(pct), color: getVariationColor(pct) },
      ];
    }
    const first = Number(series[0]?.value ?? 0);
    const pct = Number.isFinite(first) && first > 0 ? ((last / first) - 1) * 100 : 0;
    return [
      { label: '', value: formatMoney(last, mvpCurrency), color: 'blue' },
      { label: 'Var', value: formatPct(pct), color: getVariationColor(pct) },
    ];
  }, [portfolioChartData, mvpCurrency, isIntradayWindow, portfolioSummary]);

  const chartStats = mvpTimeseriesStats
    ? [
        { label: '', value: formatMoney(mvpTimeseriesStats.last, mvpCurrency), color: 'blue' },
        { label: 'Var', value: formatPct(mvpTimeseriesStats.pct), color: getVariationColor(mvpTimeseriesStats.pct) },
      ]
    : undefined;

  const kpiItems = useMemo(() => [
    {
      label: isMobile ? 'Oggi' : 'Var. Giornaliera',
      value: portfolioSummary
        ? isMobile
          ? formatPct(portfolioSummary.day_change_pct)
          : `${formatMoney(portfolioSummary.day_change, mvpCurrency, true)} (${formatPct(portfolioSummary.day_change_pct)})`
        : 'N/D',
      color: getVariationColor(portfolioSummary?.day_change ?? 0),
      icon: IconArrowUpRight,
      iconColor: 'orange' as const,
      subtitle: portfolioSummary ? formatMoney(portfolioSummary.day_change, mvpCurrency, true) : undefined,
      subtitleColor: getVariationColor(portfolioSummary?.day_change ?? 0),
    },
    {
      label: isMobile ? 'Valore Tot' : 'Valore Totale',
      value: portfolioSummary ? formatMoney(portfolioSummary.market_value, mvpCurrency) : 'N/D',
      icon: IconCoin,
      iconColor: 'blue' as const,
    },
    {
      label: 'P/L Totale',
      value: portfolioSummary ? formatMoney(portfolioSummary.unrealized_pl, mvpCurrency, true) : 'N/D',
      color: getVariationColor(portfolioSummary?.unrealized_pl ?? 0),
      icon: IconActivity,
      iconColor: 'teal' as const,
    },
    {
      label: 'P/L %',
      value: portfolioSummary ? formatPct(portfolioSummary.unrealized_pl_pct) : 'N/D',
      color: getVariationColor(portfolioSummary?.unrealized_pl_pct ?? 0),
      icon: IconArrowUpRight,
      iconColor: 'green' as const,
    },
    {
      label: 'Cash',
      value: portfolioSummary ? formatMoney(portfolioSummary.cash_balance, mvpCurrency) : 'N/D',
      icon: IconCoin,
      iconColor: 'grape' as const,
    },
  ], [portfolioSummary, mvpCurrency, isMobile]);

  const allocationDoughnutData = useMemo<AllocationDoughnutItem[]>(
    () => portfolioAllocationData.map((item) => ({ name: item.symbol, value: item.weight_pct, asset_id: item.asset_id })),
    [portfolioAllocationData],
  );

  const { best, worst } = useMemo(() => {
    const sorted = [...portfolioPositions]
      .filter((p) => Number.isFinite(p.day_change_pct))
      .sort((a, b) => b.day_change_pct - a.day_change_pct);
    const bestItems: PerformerItem[] = sorted.slice(0, 3).map((p) => ({
      symbol: p.symbol,
      name: p.name,
      return_pct: p.day_change_pct,
      as_of: p.first_trade_at ?? null,
      asset_id: p.asset_id,
    }));
    const worstItems: PerformerItem[] = sorted.slice(-3).reverse().map((p) => ({
      symbol: p.symbol,
      name: p.name,
      return_pct: p.day_change_pct,
      as_of: p.first_trade_at ?? null,
      asset_id: p.asset_id,
    }));
    return { best: bestItems, worst: worstItems };
  }, [portfolioPositions]);

  const gainChartData = useMemo(
    () =>
      gainPoints.map((p) => ({
        rawDate: p.date,
        date: new Date(p.date).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }),
        portfolioValue: p.portfolio_value,
        netInvested: p.net_invested,
      })),
    [gainPoints],
  );

  const gainChartStats = useMemo(() => {
    if (!gainChartData.length) return undefined;
    const last = gainChartData[gainChartData.length - 1];
    const gain = last.portfolioValue - last.netInvested;
    const pct = last.netInvested > 0 ? (gain / last.netInvested) * 100 : 0;
    return [
      { label: 'Valore', value: formatMoney(last.portfolioValue, mvpCurrency), color: 'blue' },
      { label: 'P/L', value: `${formatMoney(gain, mvpCurrency, true)} (${formatPct(pct)})`, color: getVariationColor(gain) },
    ];
  }, [gainChartData, mvpCurrency]);

  const benchmarkSelectData = useMemo(
    () => [
      { value: '', label: 'Nessuno' },
      ...benchmarkList.map((b) => ({ value: String(b.asset_id), label: b.symbol })),
    ],
    [benchmarkList],
  );

  const comparisonChartData = useMemo(() => {
    if (!selectedBenchmarkId || !mvpTimeseriesData.length || !benchmarkPrices.length) return [];
    const benchMap = new Map(benchmarkPrices.map((p) => [p.date, p.close]));
    const points: Array<{ rawDate: string; date: string; portfolio: number; benchmark: number }> = [];
    let portfolioBase: number | null = null;
    let benchBase: number | null = null;
    for (const pt of mvpTimeseriesData) {
      const benchClose = benchMap.get(pt.rawDate);
      if (benchClose == null) continue;
      if (portfolioBase === null) { portfolioBase = pt.value; benchBase = benchClose; }
      if (!portfolioBase || !benchBase) continue;
      points.push({
        rawDate: pt.rawDate,
        date: pt.date,
        portfolio: (pt.value / portfolioBase) * 100,
        benchmark: (benchClose / benchBase) * 100,
      });
    }
    return points;
  }, [selectedBenchmarkId, mvpTimeseriesData, benchmarkPrices]);

  const hasBenchmark = selectedBenchmarkId !== null && (comparisonChartData.length > 0 || benchmarkLoading);

  const comparisonStats = useMemo(() => {
    if (!hasBenchmark || comparisonChartData.length === 0) return undefined;
    const last = comparisonChartData[comparisonChartData.length - 1];
    const pPct = last.portfolio - 100;
    const bPct = last.benchmark - 100;
    const benchLabel = benchmarkList.find((b) => b.asset_id === selectedBenchmarkId)?.symbol ?? 'Benchmark';
    return { pPct, bPct, benchLabel };
  }, [hasBenchmark, comparisonChartData, benchmarkList, selectedBenchmarkId]);

  const totalAllocationPct = portfolioAllocationData.reduce((sum, item) => sum + item.weight_pct, 0);

  const insufficientAssets = useMemo(
    () => (dataCoverage?.assets ?? []).filter((a) => a.coverage_pct < (dataCoverage?.threshold_pct ?? 80)),
    [dataCoverage],
  );

  const stalePositions = useMemo(
    () => portfolioPositions.filter((p) => p.price_stale),
    [portfolioPositions],
  );

  return (
    <>
      {stalePositions.length > 0 && !staleAlertDismissed && (
        <Alert
          color="yellow"
          icon={<IconAlertTriangle size={18} />}
          title="Prezzi non aggiornati"
          mb="md"
          withCloseButton
          onClose={() => setStaleAlertDismissed(true)}
        >
          {stalePositions.length === 1
            ? `Il prezzo di ${stalePositions[0].symbol} non è aggiornato.`
            : `I prezzi di ${stalePositions.map((p) => p.symbol).join(', ')} non sono aggiornati.`}
          {' '}I valori di P/L potrebbero non essere affidabili. Premi &quot;Aggiorna&quot; per scaricare i prezzi più recenti.
        </Alert>
      )}

      {dataCoverage && !dataCoverage.sufficient && insufficientAssets.length > 0 && (
        <Alert
          color="yellow"
          icon={<IconAlertTriangle size={18} />}
          title="Dati storici insufficienti"
          mb="md"
        >
          Alcuni asset hanno una copertura dati insufficiente per i grafici:{' '}
          {insufficientAssets.map((a) => `${a.symbol} (${formatNum(a.coverage_pct, 0)}%)`).join(', ')}.
          Premi il pulsante &quot;Aggiorna&quot; per scaricare lo storico prezzi.
        </Alert>
      )}

      {isMobile ? <DashboardMobileKpiCarousel items={kpiItems} /> : <KpiStatsGrid items={kpiItems} />}

      <div style={{ marginTop: 16 }}>
        {hasBenchmark ? (
          <Card withBorder radius="md" p="md" shadow="sm">
            <Group justify="space-between" mb="xs" align={isMobile ? 'flex-start' : 'center'} wrap="wrap" gap="xs">
              <Group gap="xs">
                <Text fw={600} size="sm">
                  {`Andamento Portafoglio vs ${comparisonStats?.benchLabel} (${chartWindow === '1' ? '1g' : `${chartWindowDays}g`})`}
                </Text>
                {comparisonStats && (
                  <>
                    <Badge variant="light" color={getVariationColor(comparisonStats.pPct)} size={isMobile ? 'lg' : 'md'}
                      styles={{ root: { fontSize: isMobile ? 14 : 13, fontWeight: 600, paddingInline: isMobile ? 12 : 10, height: isMobile ? 32 : 28 } }}>
                      Portafoglio {formatPct(comparisonStats.pPct)}
                    </Badge>
                    <Badge variant="light" color={getVariationColor(comparisonStats.bPct)} size={isMobile ? 'lg' : 'md'}
                      styles={{ root: { fontSize: isMobile ? 14 : 13, fontWeight: 600, paddingInline: isMobile ? 12 : 10, height: isMobile ? 32 : 28 } }}>
                      {comparisonStats.benchLabel} {formatPct(comparisonStats.bPct)}
                    </Badge>
                  </>
                )}
              </Group>
              <Group gap="xs" style={isMobile ? { width: '100%' } : undefined}>
                <Select
                  size={isMobile ? 'sm' : 'xs'}
                  w={isMobile ? '100%' : 140}
                  data={benchmarkSelectData}
                  value={selectedBenchmarkId != null ? String(selectedBenchmarkId) : ''}
                  onChange={(v) => setSelectedBenchmarkId(v ? Number(v) : null)}
                  allowDeselect={false}
                />
                <SegmentedControl
                  size={isMobile ? 'sm' : 'xs'}
                  value={chartWindow}
                  onChange={setChartWindow}
                  data={DASHBOARD_WINDOWS.map((w) => ({ label: w.label, value: w.value }))}
                  fullWidth={isMobile}
                />
              </Group>
            </Group>
            <Text size="xs" c="dimmed" mb="sm">Entrambe le serie normalizzate a base 100</Text>
            <div style={{ height: isMobile ? 320 : 260 }}>
              {benchmarkLoading ? (
                <Group h="100%" justify="center">
                  <Loader size="sm" />
                  <Text c="dimmed" size="sm">Caricamento benchmark...</Text>
                </Group>
              ) : comparisonChartData.length === 0 ? (
                <Group h="100%" justify="center">
                  <Text c="dimmed" size="sm">Nessun dato di prezzo disponibile per il benchmark. Prova ad aggiornare i prezzi.</Text>
                </Group>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={comparisonChartData}>
                    <defs>
                      <linearGradient id="compPortfolioGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#16a34a" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#16a34a" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
                    <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: tickColor, fontSize: 12 }} />
                    <YAxis hide domain={['auto', 'auto']} />
                    <Tooltip
                      content={({ active, payload, label }: any) => {
                        if (!active || !payload?.length) return null;
                        const pv = Number(payload.find((p: any) => p.dataKey === 'portfolio')?.value ?? 0);
                        const bv = Number(payload.find((p: any) => p.dataKey === 'benchmark')?.value ?? 0);
                        return (
                          <Paper withBorder p="xs" radius="sm" shadow="xs">
                            <Text size="xs" c="dimmed">{`Data ${label}`}</Text>
                            <Text size="sm" fw={600} c="#16a34a">{`Portafoglio: ${formatPct(pv - 100)}`}</Text>
                            <Text size="sm" fw={600} c="#2563eb">{`${comparisonStats?.benchLabel}: ${formatPct(bv - 100)}`}</Text>
                          </Paper>
                        );
                      }}
                    />
                    <Legend
                      verticalAlign="top"
                      height={28}
                      formatter={(value: string) => (value === 'portfolio' ? 'Portafoglio' : (comparisonStats?.benchLabel ?? 'Benchmark'))}
                    />
                    <Area
                      type="monotone"
                      dataKey="portfolio"
                      stroke="#16a34a"
                      strokeWidth={2.5}
                      fillOpacity={1}
                      fill="url(#compPortfolioGrad)"
                    />
                    <Area
                      type="monotone"
                      dataKey="benchmark"
                      stroke="#2563eb"
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      fillOpacity={0}
                      fill="transparent"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>
        ) : (
          <PerformanceChart
            title={`Andamento Portafoglio (${chartWindow === '1' ? '1g' : `${chartWindowDays}g`})`}
            data={portfolioChartData}
            xKey={isIntradayWindow && portfolioIntradayData.length > 0 ? 'time' : 'date'}
            gradientId="mvpTimeseriesGradient"
            color="#16a34a"
            stats={portfolioChartStats ?? chartStats}
            loading={false}
            emptyMessage="Nessun dato disponibile"
            subtitle="Calcolato da transazioni + storico prezzi"
            headerRight={
              <Group gap="xs">
                <Select
                  size="xs"
                  w={140}
                  data={benchmarkSelectData}
                  value={selectedBenchmarkId != null ? String(selectedBenchmarkId) : ''}
                  onChange={(v) => setSelectedBenchmarkId(v ? Number(v) : null)}
                  allowDeselect={false}
                />
                <SegmentedControl
                  size="xs"
                  value={chartWindow}
                  onChange={setChartWindow}
                  data={DASHBOARD_WINDOWS.map((w) => ({ label: w.label, value: w.value }))}
                />
              </Group>
            }
            tooltipContent={({ active, payload, label }: any) => {
              if (!active || !payload?.length) return null;
              const value = Number(payload[0]?.value ?? 0);
              if (!Number.isFinite(value)) return null;
              const pointData = payload[0]?.payload;
              const idx = portfolioChartData.indexOf(pointData);
              const prevValue = idx > 0 ? Number((portfolioChartData[idx - 1] as any).value ?? 0) : null;
              const changePct = prevValue && prevValue > 0 ? ((value - prevValue) / prevValue) * 100 : null;
              return (
                <Paper withBorder p="xs" radius="sm" shadow="xs">
                  <Text size="xs" c="dimmed">{`${isIntradayWindow && portfolioIntradayData.length > 0 ? 'Ora' : 'Data'} ${label}`}</Text>
                  <Text size="sm" fw={600}>{formatMoney(value, mvpCurrency)}</Text>
                  {changePct != null && Number.isFinite(changePct) && (
                    <Text size="xs" fw={500} c={getVariationColor(changePct)}>{formatPct(changePct)}</Text>
                  )}
                </Paper>
              );
            }}
          />
        )}
      </div>

      <Card withBorder radius="md" p="md" shadow="sm" mt="md">
        <Group justify="space-between" mb="xs" align="center" wrap="wrap" gap="xs">
          <Group gap="xs">
            <Text fw={600} size="sm">
              {`Valore vs Investito (${chartWindow === '1' ? '1g' : `${chartWindowDays}g`})`}
            </Text>
            {gainChartStats?.map((s) => (
              <Badge
                key={s.label}
                variant="light"
                color={s.color ?? 'blue'}
                size={isMobile ? 'lg' : 'md'}
                styles={{
                  root: {
                    fontSize: isMobile ? 14 : 13,
                    fontWeight: 600,
                    paddingInline: isMobile ? 12 : 10,
                    height: isMobile ? 32 : 28,
                  },
                }}
              >
                {s.label} {s.value}
              </Badge>
            ))}
          </Group>
        </Group>
        <Text size="xs" c="dimmed" mb="sm">Valore di mercato del portafoglio confrontato con il netto investito</Text>
        <div style={{ height: isMobile ? 300 : 220 }}>
          {gainChartLoading ? (
            <Group h="100%" justify="center">
              <Loader size="sm" />
              <Text c="dimmed" size="sm">Caricamento...</Text>
            </Group>
          ) : gainChartData.length === 0 ? (
            <Group h="100%" justify="center">
              <Text c="dimmed" size="sm">Nessun dato disponibile</Text>
            </Group>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={gainChartData}>
                <defs>
                  <linearGradient id="gainValueGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#16a34a" stopOpacity={0.18} />
                    <stop offset="95%" stopColor="#16a34a" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
                <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: tickColor, fontSize: 12 }} />
                <YAxis hide domain={['auto', 'auto']} />
                <Tooltip
                  content={({ active, payload, label }: any) => {
                    if (!active || !payload?.length) return null;
                    const pv = Number(payload.find((p: any) => p.dataKey === 'portfolioValue')?.value ?? 0);
                    const ni = Number(payload.find((p: any) => p.dataKey === 'netInvested')?.value ?? 0);
                    const gain = pv - ni;
                    return (
                      <Paper withBorder p="xs" radius="sm" shadow="xs">
                        <Text size="xs" c="dimmed">{`Data ${label}`}</Text>
                        <Text size="sm" fw={600} c="#16a34a">{`Valore: ${formatMoney(pv, mvpCurrency)}`}</Text>
                        <Text size="sm" fw={600} c="#868e96">{`Investito: ${formatMoney(ni, mvpCurrency)}`}</Text>
                        <Text size="sm" fw={600} c={getVariationColor(gain)}>{`P/L: ${formatMoney(gain, mvpCurrency, true)}`}</Text>
                      </Paper>
                    );
                  }}
                />
                <Legend
                  verticalAlign="top"
                  height={28}
                  formatter={(value: string) => (value === 'portfolioValue' ? 'Valore Portafoglio' : 'Netto Investito')}
                />
                <Area
                  type="monotone"
                  dataKey="portfolioValue"
                  stroke="#16a34a"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#gainValueGradient)"
                />
                <Area
                  type="monotone"
                  dataKey="netInvested"
                  stroke="#868e96"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  fillOpacity={0}
                  fill="transparent"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      <Grid gutter="md" mt="md">
        <Grid.Col span={{ base: 12, md: 7 }}>
          <BestWorstCards best={best} worst={worst} periodLabel="oggi" />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <AllocationDoughnut
            title="Allocazione Portafoglio"
            data={allocationDoughnutData}
            centerLabel={totalAllocationPct > 0 ? `${formatNum(totalAllocationPct, 0)}%` : '0%'}
          />
        </Grid.Col>
      </Grid>
    </>
  );
}
