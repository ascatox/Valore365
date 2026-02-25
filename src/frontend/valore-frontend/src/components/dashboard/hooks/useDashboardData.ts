import { useEffect, useMemo, useState } from 'react';
import {
  backfillPortfolioDailyPrices,
  getAdminPortfolios,
  getPortfolioAllocation,
  getPortfolioPositions,
  getPortfolioSummary,
  getPortfolioTimeseries,
  getPortfolioTargetAllocation,
  getPortfolioTargetAssetPerformance,
  getPortfolioTargetAssetIntradayPerformance,
  getPortfolioTargetIntradayPerformance,
  getPortfolioTargetPerformance,
  refreshPortfolioPrices,
} from '../../../services/api';
import type {
  AllocationItem,
  Portfolio,
  PortfolioSummary,
  PortfolioTargetAllocationItem,
  PortfolioTargetAssetPerformanceResponse,
  PortfolioTargetAssetIntradayPerformanceResponse,
  PortfolioTargetIntradayResponse,
  PortfolioTargetPerformanceResponse,
  Position,
  TimeSeriesPoint,
} from '../../../services/api';
import { DASHBOARD_WINDOWS, STORAGE_KEYS } from '../constants';
import type { ChartPoint, DashboardData, IntradayChartPoint } from '../types';

export function useDashboardData(): DashboardData {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId);
  });
  const [allocation, setAllocation] = useState<PortfolioTargetAllocationItem[]>([]);
  const [portfolioSummary, setPortfolioSummary] = useState<PortfolioSummary | null>(null);
  const [portfolioPositions, setPortfolioPositions] = useState<Position[]>([]);
  const [portfolioAllocation, setPortfolioAllocation] = useState<AllocationItem[]>([]);
  const [portfolioTimeseries, setPortfolioTimeseries] = useState<TimeSeriesPoint[]>([]);
  const [targetPerformance, setTargetPerformance] = useState<PortfolioTargetPerformanceResponse | null>(null);
  const [assetPerformance, setAssetPerformance] = useState<PortfolioTargetAssetPerformanceResponse | null>(null);
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
  const [chartWindow, setChartWindow] = useState<string>(() => {
    if (typeof window === 'undefined') return '1';
    const stored = window.localStorage.getItem(STORAGE_KEYS.chartWindow);
    const isValid = stored ? DASHBOARD_WINDOWS.some((w) => w.value === stored) : false;
    return isValid ? (stored as string) : '1';
  });
  const [mainIntradayData, setMainIntradayData] = useState<PortfolioTargetIntradayResponse | null>(null);
  const [mainIntradayLoading, setMainIntradayLoading] = useState(false);
  const [assetIntradayPerformance, setAssetIntradayPerformance] =
    useState<PortfolioTargetAssetIntradayPerformanceResponse | null>(null);
  const [assetIntradayLoading, setAssetIntradayLoading] = useState(false);

  // Load portfolios on mount
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
    return () => { active = false; };
  }, []);

  // Persist selected portfolio
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (selectedPortfolioId) {
      window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, selectedPortfolioId);
    } else {
      window.localStorage.removeItem(STORAGE_KEYS.selectedPortfolioId);
    }
  }, [selectedPortfolioId]);

  // Persist chart window
  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEYS.chartWindow, chartWindow);
  }, [chartWindow]);

  const loadDashboardData = async (portfolioId: number) => {
    const [allocationData, perfData, assetPerfData, summaryData, positionsData, portfolioAllocationData, timeseriesData] =
      await Promise.all([
        getPortfolioTargetAllocation(portfolioId),
        getPortfolioTargetPerformance(portfolioId),
        getPortfolioTargetAssetPerformance(portfolioId),
        getPortfolioSummary(portfolioId),
        getPortfolioPositions(portfolioId),
        getPortfolioAllocation(portfolioId),
        getPortfolioTimeseries(portfolioId),
      ]);
    setAllocation(allocationData);
    setTargetPerformance(perfData);
    setAssetPerformance(assetPerfData);
    setPortfolioSummary(summaryData);
    setPortfolioPositions(positionsData);
    setPortfolioAllocation(portfolioAllocationData);
    setPortfolioTimeseries(timeseriesData);
  };

  const loadMainIntradayChart = async (portfolioId: number) => {
    const now = new Date();
    const localDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const data = await getPortfolioTargetIntradayPerformance(portfolioId, localDate);
    setMainIntradayData(data);
  };

  const loadAssetIntradayCharts = async (portfolioId: number) => {
    const now = new Date();
    const localDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const data = await getPortfolioTargetAssetIntradayPerformance(portfolioId, localDate);
    setAssetIntradayPerformance(data);
  };

  // Load dashboard data when portfolio changes
  useEffect(() => {
    if (!selectedPortfolioId) {
      setAllocation([]);
      setPortfolioSummary(null);
      setPortfolioPositions([]);
      setPortfolioAllocation([]);
      setPortfolioTimeseries([]);
      setTargetPerformance(null);
      setAssetPerformance(null);
      setAssetIntradayPerformance(null);
      return;
    }
    const portfolioId = Number(selectedPortfolioId);
    if (!Number.isFinite(portfolioId)) return;

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
    return () => { active = false; };
  }, [selectedPortfolioId, chartWindow]);

  // Load intraday data when window is '1'
  useEffect(() => {
    const portfolioId = Number(selectedPortfolioId);
    if (chartWindow !== '1' || !Number.isFinite(portfolioId)) {
      setMainIntradayData(null);
      setAssetIntradayPerformance(null);
      setMainIntradayLoading(false);
      setAssetIntradayLoading(false);
      return;
    }
    let active = true;
    setMainIntradayLoading(true);
    setAssetIntradayLoading(true);
    Promise.all([loadMainIntradayChart(portfolioId), loadAssetIntradayCharts(portfolioId)])
      .catch(() => {
        if (!active) return;
        setMainIntradayData(null);
        setAssetIntradayPerformance(null);
      })
      .finally(() => {
        if (active) {
          setMainIntradayLoading(false);
          setAssetIntradayLoading(false);
        }
      });
    return () => { active = false; };
  }, [chartWindow, selectedPortfolioId]);

  // Refresh event listener
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
          await Promise.all([loadMainIntradayChart(portfolioId), loadAssetIntradayCharts(portfolioId)]);
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
    return () => { window.removeEventListener('valore365:refresh-dashboard', onRefresh); };
  }, [selectedPortfolioId, chartWindow]);

  // Computed values
  const chartWindowDays = useMemo(
    () => DASHBOARD_WINDOWS.find((w) => w.value === chartWindow)?.days ?? 90,
    [chartWindow],
  );

  const chartData = useMemo<ChartPoint[]>(
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

  const selectedPortfolio = useMemo(
    () => portfolios.find((p) => String(p.id) === selectedPortfolioId) ?? null,
    [portfolios, selectedPortfolioId],
  );

  const indexCardStats = useMemo(() => {
    if (chartWindow === '1') {
      const values = (mainIntradayData?.points ?? []).map((p) => p.weighted_index).filter((v) => Number.isFinite(v));
      if (!values.length || values[0] <= 0) return null;
      const last = values[values.length - 1];
      return { index: last, diffPts: last - 100, diffPct: ((last / values[0]) - 1) * 100 };
    }
    const values = chartData.map((p) => p.value).filter((v) => Number.isFinite(v));
    if (!values.length || values[0] <= 0) return null;
    const last = values[values.length - 1];
    return { index: last, diffPts: last - 100, diffPct: ((last / values[0]) - 1) * 100 };
  }, [chartWindow, chartData, mainIntradayData]);

  const intradayChartData = useMemo<IntradayChartPoint[]>(
    () =>
      (intradayData?.points ?? []).map((p) => ({
        ts: p.ts,
        time: new Date(p.ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }),
        value: p.weighted_index,
      })),
    [intradayData],
  );

  const mainIntradayChartData = useMemo<IntradayChartPoint[]>(
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
    return { last, periodPct: ((last / first) - 1) * 100 };
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
    if (chartWindow === '1') {
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
  }, [chartWindow, assetIntradayPerformance, assetPerformance, chartData]);

  const handleDailyChartClick = async (state: any) => {
    const payload = state?.activePayload?.[0]?.payload;
    const rawDate = payload?.rawDate as string | undefined;
    const portfolioId = Number(selectedPortfolioId);
    if (!rawDate || !Number.isFinite(portfolioId)) return;
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

  const mvpCurrency = portfolioSummary?.base_currency ?? selectedPortfolio?.base_currency ?? 'EUR';

  const mvpTimeseriesData = useMemo<ChartPoint[]>(
    () =>
      portfolioTimeseries
        .filter((point) => Number.isFinite(point.market_value))
        .slice(-90)
        .map((point) => ({
          rawDate: point.date,
          date: new Date(point.date).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }),
          value: point.market_value,
        })),
    [portfolioTimeseries],
  );

  const mvpTimeseriesStats = useMemo(() => {
    if (!mvpTimeseriesData.length) return null;
    const first = Number(mvpTimeseriesData[0]?.value ?? 0);
    const last = Number(mvpTimeseriesData[mvpTimeseriesData.length - 1]?.value ?? 0);
    if (!Number.isFinite(last)) return null;
    if (!Number.isFinite(first) || first <= 0) return { last, pct: 0 };
    return { last, pct: ((last / first) - 1) * 100 };
  }, [mvpTimeseriesData]);

  return {
    portfolios,
    selectedPortfolioId,
    setSelectedPortfolioId,
    selectedPortfolio,
    allocation,
    portfolioSummary,
    portfolioPositions,
    portfolioAllocation,
    portfolioTimeseries,
    targetPerformance,
    assetPerformance,
    assetIntradayPerformance,
    mainIntradayData,
    chartWindow,
    setChartWindow,
    chartData,
    mainIntradayChartData,
    assetMiniCharts,
    loading,
    dataLoading,
    refreshing,
    mainIntradayLoading,
    assetIntradayLoading,
    error,
    refreshMessage,
    chartWindowDays,
    mvpCurrency,
    mvpTimeseriesData,
    mvpTimeseriesStats,
    handleDailyChartClick,
    intradayOpen,
    setIntradayOpen,
    intradayLoading,
    intradayError,
    intradayChartData,
    intradayStats,
    intradayDateLabel,
    indexCardStats,
    mainChartStats,
  };
}
