import { useEffect, useMemo, useState } from 'react';
import {
  SimpleGrid,
  Paper,
  Text,
  Title,
  Group,
  RingProgress,
  Badge,
  Table,
  Card,
  ThemeIcon,
  Grid,
  Autocomplete,
  Select,
  Alert,
  Loader,
  Modal,
  SegmentedControl,
} from '@mantine/core';
import { IconArrowUpRight, IconArrowDownRight, IconCoin, IconChartPie, IconActivity } from '@tabler/icons-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import {
  backfillPortfolioDailyPrices,
  getAdminPortfolios,
  getPortfolioTargetAllocation,
  getPortfolioTargetAssetPerformance,
  getPortfolioTargetIntradayPerformance,
  getPortfolioTargetPerformance,
  refreshPortfolioPrices,
} from '../services/api';
import type {
  Portfolio,
  PortfolioTargetAllocationItem,
  PortfolioTargetAssetPerformanceResponse,
  PortfolioTargetIntradayResponse,
  PortfolioTargetPerformanceResponse,
} from '../services/api';

const ALLOCATION_COLORS = ['blue', 'cyan', 'teal', 'lime', 'yellow', 'orange', 'pink'];
const DASHBOARD_WINDOWS = [
  { label: '1g', value: '1', days: 1 },
  { label: '1s', value: '7', days: 7 },
  { label: '30g', value: '30', days: 30 },
  { label: '90g', value: '90', days: 90 },
  { label: '1a', value: '365', days: 365 },
] as const;
const DASHBOARD_SELECTED_PORTFOLIO_STORAGE_KEY = 'valore365.dashboard.selectedPortfolioId';

const formatPct = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
const getVariationColor = (value: number) => (value > 0 ? 'green' : value < 0 ? 'red' : 'gray');
const formatDateTime = (value?: string | null) => {
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
const renderIndexTooltip = (labelPrefix?: string) => ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const rawValue = Number(payload[0]?.value ?? 0);
  if (!Number.isFinite(rawValue)) return null;
  const pct = ((rawValue / 100) - 1) * 100;
  return (
    <Paper withBorder p="xs" radius="sm" shadow="xs">
      <Text size="xs" c="dimmed">{labelPrefix ? `${labelPrefix} ${label}` : label}</Text>
      <Text size="sm" fw={600}>Indice: {rawValue.toFixed(2)}</Text>
      <Text size="sm" c={getVariationColor(pct)} fw={500}>
        Variazione: {formatPct(pct)}
      </Text>
    </Paper>
  );
};

export function DashboardPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(DASHBOARD_SELECTED_PORTFOLIO_STORAGE_KEY);
  });
  const [allocation, setAllocation] = useState<PortfolioTargetAllocationItem[]>([]);
  const [targetPerformance, setTargetPerformance] = useState<PortfolioTargetPerformanceResponse | null>(null);
  const [assetPerformance, setAssetPerformance] = useState<PortfolioTargetAssetPerformanceResponse | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [intradayOpen, setIntradayOpen] = useState(false);
  const [intradayLoading, setIntradayLoading] = useState(false);
  const [intradayError, setIntradayError] = useState<string | null>(null);
  const [intradayData, setIntradayData] = useState<PortfolioTargetIntradayResponse | null>(null);
  const [intradayDateLabel, setIntradayDateLabel] = useState<string | null>(null);
  const [chartWindow, setChartWindow] = useState<string>('90');
  const [mainIntradayData, setMainIntradayData] = useState<PortfolioTargetIntradayResponse | null>(null);
  const [mainIntradayLoading, setMainIntradayLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    getAdminPortfolios()
      .then((items) => {
        if (!active) return;
        setPortfolios(items);
        setSelectedPortfolioId((prev) => {
          const prevExists = prev ? items.some((p) => String(p.id) === prev) : false;
          return prevExists ? prev : (items[0] ? String(items[0].id) : null);
        });
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Errore nel caricamento portafogli');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (selectedPortfolioId) {
      window.localStorage.setItem(DASHBOARD_SELECTED_PORTFOLIO_STORAGE_KEY, selectedPortfolioId);
    } else {
      window.localStorage.removeItem(DASHBOARD_SELECTED_PORTFOLIO_STORAGE_KEY);
    }
  }, [selectedPortfolioId]);

  const loadDashboardData = async (portfolioId: number) => {
    const [allocationData, perfData, assetPerfData] = await Promise.all([
      getPortfolioTargetAllocation(portfolioId),
      getPortfolioTargetPerformance(portfolioId),
      getPortfolioTargetAssetPerformance(portfolioId),
    ]);
    setAllocation(allocationData);
    setTargetPerformance(perfData);
    setAssetPerformance(assetPerfData);
  };

  const loadMainIntradayChart = async (portfolioId: number) => {
    const now = new Date();
    const localDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const data = await getPortfolioTargetIntradayPerformance(portfolioId, localDate);
    setMainIntradayData(data);
  };

  useEffect(() => {
    if (!selectedPortfolioId) {
      setAllocation([]);
      setTargetPerformance(null);
      setAssetPerformance(null);
      return;
    }

    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) {
      return;
    }

    let active = true;
    setDataLoading(true);
    setError(null);

    loadDashboardData(portfolioId)
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Errore nel caricamento dati portfolio');
      })
      .finally(() => {
        if (active) setDataLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedPortfolioId, chartWindow]);

  useEffect(() => {
    const portfolioId = Number(selectedPortfolioId);
    if (chartWindow !== '1' || !Number.isFinite(portfolioId)) {
      setMainIntradayData(null);
      setMainIntradayLoading(false);
      return;
    }

    let active = true;
    setMainIntradayLoading(true);
    loadMainIntradayChart(portfolioId)
      .catch(() => {
        if (!active) return;
        setMainIntradayData(null);
      })
      .finally(() => {
        if (active) setMainIntradayLoading(false);
      });

    return () => {
      active = false;
    };
  }, [chartWindow, selectedPortfolioId]);

  useEffect(() => {
    const onRefresh = async () => {
      const portfolioId = Number(selectedPortfolioId);
      if (!Number.isFinite(portfolioId)) {
        setRefreshMessage('Seleziona un portfolio prima di aggiornare');
        return;
      }
      setError(null);
      setRefreshMessage(null);
      setRefreshing(true);
      try {
        const refreshResult = await refreshPortfolioPrices(portfolioId, 'target');
        const backfillResult = await backfillPortfolioDailyPrices(portfolioId, 365, 'target');
        await loadDashboardData(portfolioId);
        if (chartWindow === '1') {
          await loadMainIntradayChart(portfolioId);
        }
        setRefreshMessage(
          `Aggiornati prezzi: ${refreshResult.refreshed_assets}/${refreshResult.requested_assets}, storico: ${backfillResult.assets_refreshed}/${backfillResult.assets_requested}`,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Errore durante aggiornamento prezzi');
      } finally {
        setRefreshing(false);
      }
    };

    window.addEventListener('valore365:refresh-dashboard', onRefresh);
    return () => {
      window.removeEventListener('valore365:refresh-dashboard', onRefresh);
    };
  }, [selectedPortfolioId]);

  const handleSearch = (value: string) => {
    setQuery(value);
  };

  const chartWindowDays = useMemo(
    () => DASHBOARD_WINDOWS.find((w) => w.value === chartWindow)?.days ?? 90,
    [chartWindow],
  );

  const chartData = useMemo(
    () =>
      (targetPerformance?.points ?? [])
        .filter((point) => point.weighted_index > 0)
        .slice(-chartWindowDays)
        .map((point) => ({
          rawDate: point.date,
          date: new Date(point.date).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }),
          value: point.weighted_index,
        })),
    [targetPerformance, chartWindowDays],
  );

  const allocationSections = useMemo(
    () =>
      allocation.slice(0, 6).map((item, index) => ({
        value: Math.max(0, item.weight_pct),
        color: ALLOCATION_COLORS[index % ALLOCATION_COLORS.length],
        tooltip: `${item.symbol} (${item.weight_pct.toFixed(2)}%)`,
      })),
    [allocation],
  );

  const portfolioSearchOptions = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? allocation.filter(
          (p) => p.symbol.toLowerCase().includes(q) || p.name.toLowerCase().includes(q),
        )
      : allocation;

    return filtered.slice(0, 20).map((p) => `${p.symbol} - ${p.name}`);
  }, [allocation, query]);

  const best = targetPerformance?.best ?? null;
  const worst = targetPerformance?.worst ?? null;
  const totalAssignedWeight = allocation.reduce((sum, item) => sum + item.weight_pct, 0);
  const indexCardStats = useMemo(() => {
    if (chartWindow === '1') {
      const values = (mainIntradayData?.points ?? []).map((p) => p.weighted_index).filter((v) => Number.isFinite(v));
      if (!values.length || values[0] <= 0) return null;
      const last = values[values.length - 1];
      return {
        index: last,
        diffPts: last - 100,
        diffPct: ((last / values[0]) - 1) * 100,
      };
    }

    const values = chartData.map((p) => p.value).filter((v) => Number.isFinite(v));
    if (!values.length || values[0] <= 0) return null;
    const last = values[values.length - 1];
    return {
      index: last,
      diffPts: last - 100,
      diffPct: ((last / values[0]) - 1) * 100,
    };
  }, [chartWindow, chartData, mainIntradayData]);

  const kpiData = [
    {
      label: 'Indice Portafoglio',
      amount: indexCardStats ? indexCardStats.index.toFixed(2) : 'N/D',
      diff: indexCardStats?.diffPts ?? 0,
      diffPct: indexCardStats?.diffPct ?? 0,
      icon: IconCoin,
      color: 'blue',
    },
    {
      label: 'Peso Assegnato',
      amount: `${totalAssignedWeight.toFixed(2)}%`,
      diff: 0,
      icon: IconActivity,
      color: 'teal',
    },
    {
      label: 'Titolo Migliore',
      amount: best?.symbol ?? 'N/D',
      diff: best?.return_pct ?? 0,
      meta: formatDateTime(best?.as_of),
      icon: IconArrowUpRight,
      color: 'green',
    },
    {
      label: 'Titolo Peggiore',
      amount: worst?.symbol ?? 'N/D',
      diff: worst?.return_pct ?? 0,
      meta: formatDateTime(worst?.as_of),
      icon: IconChartPie,
      color: 'orange',
    },
  ];

  const stats = kpiData.map((stat) => {
    const DiffIcon = stat.diff >= 0 ? IconArrowUpRight : IconArrowDownRight;
    const diffColor = getVariationColor(stat.diff);

    return (
      <Paper withBorder p="md" radius="md" key={stat.label} shadow="xs">
        <Group justify="space-between">
          <Text size="xs" c="dimmed" fw={700} tt="uppercase">
            {stat.label}
          </Text>
          <ThemeIcon color={stat.color} variant="light" size="md" radius="md">
            <stat.icon size={18} />
          </ThemeIcon>
        </Group>

        <Group align="flex-end" gap="xs" mt={25}>
          <Text fw={700} size="xl">{stat.amount}</Text>
          {stat.label !== 'Peso Assegnato' && (
            <>
              <Badge color={diffColor} variant="light" size="sm" leftSection={<DiffIcon size={12} />}>
                {stat.label === 'Indice Portafoglio' ? `${stat.diff >= 0 ? '+' : ''}${stat.diff.toFixed(2)} pts` : formatPct(stat.diff)}
              </Badge>
              {stat.label === 'Indice Portafoglio' && 'diffPct' in stat && (
                <Badge color={diffColor} variant="light" size="sm">
                  {formatPct(stat.diffPct)}
                </Badge>
              )}
            </>
          )}
        </Group>
        {'meta' in stat && stat.meta && (
          <Text size="xs" c="dimmed" mt="xs">
            {stat.meta}
          </Text>
        )}
      </Paper>
    );
  });

  const rows = [best, worst].filter(Boolean).map((element, idx) => (
    <Table.Tr key={`${element!.asset_id}-${idx}`}>
      <Table.Td>
        <Text size="sm" fw={500}>{element!.symbol}</Text>
        <Text size="xs" c="dimmed">{element!.name}</Text>
        <Text size="xs" c="dimmed">{formatDateTime(element!.as_of)}</Text>
      </Table.Td>
      <Table.Td align="right">Indice target</Table.Td>
      <Table.Td align="right">
        <Text c={getVariationColor(element!.return_pct)} size="sm" fw={500}>
          {formatPct(element!.return_pct)}
        </Text>
      </Table.Td>
    </Table.Tr>
  ));

  const intradayChartData = useMemo(
    () =>
      (intradayData?.points ?? []).map((p) => ({
        ts: p.ts,
        time: new Date(p.ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
        value: p.weighted_index,
      })),
    [intradayData],
  );

  const mainIntradayChartData = useMemo(
    () =>
      (mainIntradayData?.points ?? []).map((p) => ({
        ts: p.ts,
        time: new Date(p.ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
        value: p.weighted_index,
      })),
    [mainIntradayData],
  );

  const mainChartStats = useMemo(() => {
    const series = chartWindow === '1' ? mainIntradayChartData : chartData;
    if (!series.length) return null;
    const first = Number(series[0]?.value ?? 0);
    const last = Number(series[series.length - 1]?.value ?? 0);
    if (!Number.isFinite(first) || !Number.isFinite(last) || first <= 0) return null;
    return {
      last,
      periodPct: ((last / first) - 1) * 100,
    };
  }, [chartWindow, mainIntradayChartData, chartData]);

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

  const assetMiniCharts = useMemo(() => {
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
  }, [assetPerformance, chartData]);

  const handleDailyChartClick = async (state: any) => {
    const payload = state?.activePayload?.[0]?.payload;
    const rawDate = payload?.rawDate as string | undefined;
    const portfolioId = Number(selectedPortfolioId);
    if (!rawDate || !Number.isFinite(portfolioId)) {
      return;
    }

    setIntradayOpen(true);
    setIntradayLoading(true);
    setIntradayError(null);
    setIntradayData(null);
    setIntradayDateLabel(new Date(rawDate).toLocaleDateString('it-IT'));
    try {
      const data = await getPortfolioTargetIntradayPerformance(portfolioId, rawDate);
      setIntradayData(data);
    } catch (err) {
      setIntradayError(err instanceof Error ? err.message : 'Errore caricamento intraday');
    } finally {
      setIntradayLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <Title order={2} fw={700} mb="md">Dashboard</Title>
      <Group align="end" mb="md" grow>
        <Select
          label="Portfolio"
          placeholder={loading ? 'Caricamento portafogli...' : 'Seleziona portfolio'}
          data={portfolios.map((p) => ({ value: String(p.id), label: `${p.name} (#${p.id})` }))}
          value={selectedPortfolioId}
          onChange={setSelectedPortfolioId}
          disabled={loading || portfolios.length === 0}
        />
        <Autocomplete
          label="Cerca tra gli asset in portafoglio"
          placeholder="Es. AAPL"
          data={portfolioSearchOptions}
          value={query}
          onChange={handleSearch}
        />
      </Group>

      {error && <Alert color="red" mb="md">{error}</Alert>}
      {refreshMessage && <Alert color="teal" mb="md">{refreshMessage}</Alert>}
      {!error && targetPerformance?.last_updated_at && (
        <Text size="sm" c="dimmed" mb="md">
          Ultimo aggiornamento dati: {formatDateTime(targetPerformance.last_updated_at)}
        </Text>
      )}

      {(loading || dataLoading || refreshing) && (
        <Group mb="md">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            {refreshing ? 'Aggiornamento prezzi e grafico in corso...' : 'Caricamento dati dashboard...'}
          </Text>
        </Group>
      )}

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md" mb="lg">
        {stats}
      </SimpleGrid>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Card withBorder radius="md" p="md" shadow="sm">
            <Group justify="space-between" mb="md" align="center">
              <Group gap="xs">
                <Text fw={500}>Andamento Portafoglio (media pesata target, base 100)</Text>
                {mainChartStats && (
                  <>
                    <Badge variant="light" color="blue">
                      Indice {mainChartStats.last.toFixed(2)}
                    </Badge>
                    <Badge variant="light" color={getVariationColor(mainChartStats.periodPct)}>
                      Var {formatPct(mainChartStats.periodPct)}
                    </Badge>
                  </>
                )}
              </Group>
              <SegmentedControl
                size="xs"
                value={chartWindow}
                onChange={setChartWindow}
                data={DASHBOARD_WINDOWS.map((w) => ({ label: w.label, value: w.value }))}
              />
            </Group>
            <div style={{ height: 300 }}>
              {chartWindow === '1' ? (
                mainIntradayLoading ? (
                  <Group h="100%" justify="center">
                    <Loader size="sm" />
                    <Text c="dimmed" size="sm">Caricamento intraday...</Text>
                  </Group>
                ) : mainIntradayChartData.length === 0 ? (
                  <Group h="100%" justify="center">
                    <Text c="dimmed">Nessun dato intraday disponibile per oggi</Text>
                  </Group>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={mainIntradayChartData}>
                      <defs>
                        <linearGradient id="colorValueIntradayMain" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#228be6" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#228be6" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e0e0e0" />
                      <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: '#868e96', fontSize: 12 }} />
                      <YAxis hide domain={['auto', 'auto']} />
                      <Tooltip content={renderIndexTooltip('Ora')} />
                      <Area
                        type="monotone"
                        dataKey="value"
                        stroke="#228be6"
                        strokeWidth={3}
                        fillOpacity={1}
                        fill="url(#colorValueIntradayMain)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )
              ) : chartData.length === 0 ? (
                <Group h="100%" justify="center">
                  <Text c="dimmed">Nessun dato storico disponibile</Text>
                </Group>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} onClick={handleDailyChartClick}>
                    <defs>
                      <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#228be6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#228be6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e0e0e0" />
                    <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: '#868e96', fontSize: 12 }} />
                    <YAxis hide domain={['auto', 'auto']} />
                    <Tooltip
                      content={renderIndexTooltip('Data')}
                    />
                    <Area type="monotone" dataKey="value" stroke="#228be6" strokeWidth={3} fillOpacity={1} fill="url(#colorValue)" />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>

          <Card withBorder radius="md" p="md" mt="md" shadow="sm">
            <Text fw={500} mb="md">
              Andamento per Titolo (intervallo allineato: {chartWindowDays === 1 ? 'oggi' : `ultimi ${chartWindowDays} giorni`})
            </Text>
            {assetMiniCharts.length === 0 ? (
              <Text c="dimmed" size="sm">Nessun dato per i titoli del portafoglio</Text>
            ) : (
              <Grid gutter="md">
                {assetMiniCharts.map((asset) => (
                  <Grid.Col key={asset.asset_id} span={{ base: 12, lg: 6 }}>
                    <Paper withBorder radius="md" p="sm">
                      <Group justify="space-between" mb="xs" align="flex-start">
                        <div>
                          <Text fw={600} size="sm">{asset.symbol}</Text>
                          <Text size="xs" c="dimmed">{asset.name}</Text>
                          <Text size="xs" c="dimmed">
                            Peso {asset.weight_pct.toFixed(2)}% • {formatDateTime(asset.as_of)}
                          </Text>
                        </div>
                        <Badge color={getVariationColor(asset.return_pct)} variant="light">
                          {formatPct(asset.return_pct)}
                        </Badge>
                      </Group>
                      <div style={{ height: 180 }}>
                        {asset.chart.length === 0 ? (
                          <Group h="100%" justify="center">
                            <Text c="dimmed" size="xs">Nessuno storico</Text>
                          </Group>
                        ) : (
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={asset.chart} syncId="portfolio-target-series">
                              <defs>
                                <linearGradient id={`asset-${asset.asset_id}`} x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor="#339af0" stopOpacity={0.22} />
                                  <stop offset="95%" stopColor="#339af0" stopOpacity={0} />
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9ecef" />
                              <XAxis
                                dataKey="date"
                                axisLine={false}
                                tickLine={false}
                                tick={{ fill: '#868e96', fontSize: 11 }}
                                minTickGap={24}
                              />
                              <YAxis hide domain={['auto', 'auto']} />
                              <Tooltip
                                formatter={(value) => [Number(value).toFixed(2), 'Indice']}
                                labelFormatter={(label) => `Data ${label}`}
                                contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}
                              />
                              <Area
                                type="monotone"
                                dataKey="value"
                                stroke="#1c7ed6"
                                strokeWidth={2}
                                fillOpacity={1}
                                fill={`url(#asset-${asset.asset_id})`}
                              />
                            </AreaChart>
                          </ResponsiveContainer>
                        )}
                      </div>
                    </Paper>
                  </Grid.Col>
                ))}
              </Grid>
            )}
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card withBorder radius="md" p="md" mb="md" shadow="sm">
            <Text fw={500} mb="xs">Allocazione Asset</Text>
            <Group justify="center">
              <RingProgress
                size={180}
                thickness={16}
                roundCaps
                sections={allocationSections.length ? allocationSections : [{ value: 100, color: 'gray', tooltip: 'Nessun dato' }]}
                label={
                    <Text c="blue" fw={700} ta="center" size="xl">
                    {allocation.length ? `${Math.round(totalAssignedWeight)}%` : '0%'}
                  </Text>
                }
              />
            </Group>
            <Group justify="center" mt="xs" gap="xs">
              {allocation.slice(0, 3).map((item, index) => (
                <Badge key={item.asset_id} color={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]} size="sm" variant="dot">
                  {item.symbol}
                </Badge>
              ))}
            </Group>
          </Card>

          <Card withBorder radius="md" p="0" shadow="sm">
            <Table verticalSpacing="xs" striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Asset</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Tipo</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Rendimento</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.length ? rows : (
                  <Table.Tr>
                    <Table.Td colSpan={3}>
                      <Text c="dimmed" size="sm" ta="center">Nessuna posizione disponibile</Text>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Card>
        </Grid.Col>
      </Grid>

      <Modal
        opened={intradayOpen}
        onClose={() => setIntradayOpen(false)}
        title={intradayDateLabel ? `Andamento intraday - ${intradayDateLabel}` : 'Andamento intraday'}
        size="xl"
      >
        {intradayError && <Alert color="red" mb="md">{intradayError}</Alert>}
        {intradayLoading && (
          <Group mb="md">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">Caricamento dati intraday...</Text>
          </Group>
        )}
        {!intradayLoading && !intradayError && intradayChartData.length === 0 && (
          <Alert color="yellow">Nessun dato intraday disponibile per questa giornata.</Alert>
        )}
        {!intradayLoading && !intradayError && intradayStats && (
          <SimpleGrid cols={{ base: 2, sm: 5 }} spacing="sm" mb="md">
            <Paper withBorder p="xs" radius="md">
              <Text size="xs" c="dimmed">Apertura</Text>
              <Text fw={600} size="sm">{intradayStats.open.toFixed(2)}</Text>
            </Paper>
            <Paper withBorder p="xs" radius="md">
              <Text size="xs" c="dimmed">Ultimo</Text>
              <Text fw={600} size="sm">{intradayStats.last.toFixed(2)}</Text>
            </Paper>
            <Paper withBorder p="xs" radius="md">
              <Text size="xs" c="dimmed">Min</Text>
              <Text fw={600} size="sm">{intradayStats.min.toFixed(2)}</Text>
            </Paper>
            <Paper withBorder p="xs" radius="md">
              <Text size="xs" c="dimmed">Max</Text>
              <Text fw={600} size="sm">{intradayStats.max.toFixed(2)}</Text>
            </Paper>
            <Paper withBorder p="xs" radius="md">
              <Text size="xs" c="dimmed">Var % giorno</Text>
              <Text fw={600} size="sm" c={getVariationColor(intradayStats.dayPct)}>
                {formatPct(intradayStats.dayPct)}
              </Text>
            </Paper>
          </SimpleGrid>
        )}
        {!intradayLoading && intradayChartData.length > 0 && (
          <div style={{ height: 360 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={intradayChartData}>
                <defs>
                  <linearGradient id="colorIntraday" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#12b886" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#12b886" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e0e0e0" />
                <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: '#868e96', fontSize: 12 }} />
                <YAxis hide domain={['auto', 'auto']} />
                <Tooltip
                  content={renderIndexTooltip('Ora')}
                />
                <Area type="monotone" dataKey="value" stroke="#12b886" strokeWidth={2.5} fillOpacity={1} fill="url(#colorIntraday)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </Modal>
    </div>
  );
}
