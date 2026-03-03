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
import { DASHBOARD_WINDOWS } from '../constants';
import { formatMoney, formatNum, formatPct, getVariationColor } from '../formatters';
import type { DashboardData, PerformerItem, AllocationDoughnutItem } from '../types';

interface PanoramicaTabProps {
  data: DashboardData;
}

export function PanoramicaTab({ data }: PanoramicaTabProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');
  const {
    portfolioSummary,
    portfolioPositions,
    portfolioAllocation,
    mvpCurrency,
    mvpTimeseriesData,
    mainIntradayChartData,
    mvpTimeseriesStats,
    chartWindow,
    setChartWindow,
    chartWindowDays,
    dataCoverage,
    gainChartData,
    gainChartLoading,
    benchmarks,
    selectedBenchmarkId,
    setSelectedBenchmarkId,
    comparisonChartData,
    benchmarkLoading,
  } = data;
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  const kpiItems = useMemo(() => [
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
      label: isMobile ? 'Var. Giorn' : 'Var. Giornaliera',
      value: portfolioSummary
        ? `${formatMoney(portfolioSummary.day_change, mvpCurrency, true)} (${formatPct(portfolioSummary.day_change_pct)})`
        : 'N/D',
      color: getVariationColor(portfolioSummary?.day_change ?? 0),
      icon: IconArrowUpRight,
      iconColor: 'orange' as const,
    },
    {
      label: 'Cash',
      value: portfolioSummary ? formatMoney(portfolioSummary.cash_balance, mvpCurrency) : 'N/D',
      icon: IconCoin,
      iconColor: 'grape' as const,
    },
  ], [portfolioSummary, mvpCurrency, isMobile]);

  const chartStats = mvpTimeseriesStats
    ? [
        { label: '', value: formatMoney(mvpTimeseriesStats.last, mvpCurrency), color: 'blue' },
        { label: 'Var', value: formatPct(mvpTimeseriesStats.pct), color: getVariationColor(mvpTimeseriesStats.pct) },
      ]
    : undefined;

  const isIntradayWindow = chartWindow === '1';
  const portfolioChartData = isIntradayWindow && mainIntradayChartData.length > 0
    ? mainIntradayChartData
    : mvpTimeseriesData;

  const portfolioChartStats = useMemo(() => {
    const series = portfolioChartData;
    if (!series.length) return undefined;
    const first = Number(series[0]?.value ?? 0);
    const last = Number(series[series.length - 1]?.value ?? 0);
    if (!Number.isFinite(last)) return undefined;
    const pct = Number.isFinite(first) && first > 0 ? ((last / first) - 1) * 100 : 0;
    return [
      { label: '', value: formatMoney(last, mvpCurrency), color: 'blue' },
      { label: 'Var', value: formatPct(pct), color: getVariationColor(pct) },
    ];
  }, [portfolioChartData, mvpCurrency]);

  const allocationDoughnutData = useMemo<AllocationDoughnutItem[]>(
    () => portfolioAllocation.map((item) => ({ name: item.symbol, value: item.weight_pct, asset_id: item.asset_id })),
    [portfolioAllocation],
  );

  const { best, worst } = useMemo(() => {
    const sorted = [...portfolioPositions]
      .filter((p) => Number.isFinite(p.unrealized_pl_pct))
      .sort((a, b) => b.unrealized_pl_pct - a.unrealized_pl_pct);
    const bestItems: PerformerItem[] = sorted.slice(0, 3).map((p) => ({
      symbol: p.symbol,
      name: p.name,
      return_pct: p.unrealized_pl_pct,
      as_of: p.first_trade_at ?? null,
      asset_id: p.asset_id,
    }));
    const worstItems: PerformerItem[] = sorted.slice(-3).reverse().map((p) => ({
      symbol: p.symbol,
      name: p.name,
      return_pct: p.unrealized_pl_pct,
      as_of: p.first_trade_at ?? null,
      asset_id: p.asset_id,
    }));
    return { best: bestItems, worst: worstItems };
  }, [portfolioPositions]);

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
      ...benchmarks.map((b) => ({ value: String(b.asset_id), label: b.symbol })),
    ],
    [benchmarks],
  );

  const hasBenchmark = selectedBenchmarkId !== null && comparisonChartData.length > 0;

  const comparisonStats = useMemo(() => {
    if (!hasBenchmark) return undefined;
    const last = comparisonChartData[comparisonChartData.length - 1];
    const pPct = last.portfolio - 100;
    const bPct = last.benchmark - 100;
    const benchLabel = benchmarks.find((b) => b.asset_id === selectedBenchmarkId)?.symbol ?? 'Benchmark';
    return { pPct, bPct, benchLabel };
  }, [hasBenchmark, comparisonChartData, benchmarks, selectedBenchmarkId]);

  const gridColor = isDark ? theme.colors.dark[4] : '#e9ecef';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  const totalAllocationPct = portfolioAllocation.reduce((sum, item) => sum + item.weight_pct, 0);
  const bestWorstPeriodLabel = chartWindow === '1' ? '1g' : `${chartWindowDays}g`;

  const insufficientAssets = useMemo(
    () => (dataCoverage?.assets ?? []).filter((a) => a.coverage_pct < (dataCoverage?.threshold_pct ?? 80)),
    [dataCoverage],
  );

  const stalePositions = useMemo(
    () => portfolioPositions.filter((p) => p.price_stale),
    [portfolioPositions],
  );

  const [staleAlertDismissed, setStaleAlertDismissed] = useState(false);

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

      <KpiStatsGrid items={kpiItems} />

      <div style={{ marginTop: 16 }}>
        {hasBenchmark ? (
          <Card withBorder radius="md" p="md" shadow="sm">
            <Group justify="space-between" mb="xs" align="center" wrap="wrap" gap="xs">
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
            </Group>
            <Text size="xs" c="dimmed" mb="sm">Entrambe le serie normalizzate a base 100</Text>
            <div style={{ height: 260 }}>
              {benchmarkLoading ? (
                <Group h="100%" justify="center">
                  <Loader size="sm" />
                  <Text c="dimmed" size="sm">Caricamento benchmark...</Text>
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
            xKey={isIntradayWindow && mainIntradayChartData.length > 0 ? 'time' : 'date'}
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
                  value=""
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
              return (
                <Paper withBorder p="xs" radius="sm" shadow="xs">
                  <Text size="xs" c="dimmed">{`${isIntradayWindow && mainIntradayChartData.length > 0 ? 'Ora' : 'Data'} ${label}`}</Text>
                  <Text size="sm" fw={600}>{formatMoney(value, mvpCurrency)}</Text>
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
        <div style={{ height: 220 }}>
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
          <BestWorstCards best={best} worst={worst} periodLabel={bestWorstPeriodLabel} />
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
