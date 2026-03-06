import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Group,
  Loader,
  Tabs,
  Text,
  Title,
  useMantineTheme,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useQueryClient } from '@tanstack/react-query';
import { IconChartPie, IconList, IconChartBar, IconWorld, IconPercentage } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { DashboardMobileHeader } from '../components/mobile/DashboardMobileHeader';
import { MobileBottomNav } from '../components/mobile/MobileBottomNav';
import { usePortfolios, useTargetPerformance } from '../components/dashboard/hooks/queries';
import { PanoramicaTab } from '../components/dashboard/tabs/PanoramicaTab';
import { PosizioniTab } from '../components/dashboard/tabs/PosizioniTab';
import { AnalisiTab } from '../components/dashboard/tabs/AnalisiTab';
import { MercatiTab } from '../components/dashboard/tabs/MercatiTab';
import { PerformanceMetrics } from '../components/dashboard/analysis/PerformanceMetrics';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher';
import { formatDateTime } from '../components/dashboard/formatters';
import { DASHBOARD_WINDOWS, STORAGE_KEYS } from '../components/dashboard/constants';
import { ENABLE_TARGET_ALLOCATION } from '../features';
import { refreshPortfolioPrices, backfillPortfolioDailyPrices } from '../services/api';

export function DashboardPage() {
  const DASHBOARD_TABS = ENABLE_TARGET_ALLOCATION
    ? (['panoramica', 'posizioni', 'analisi', 'mercati', 'performance'] as const)
    : (['panoramica', 'posizioni', 'mercati', 'performance'] as const);

  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const isMobile = useMediaQuery('(max-width: 48em)');
  const theme = useMantineTheme();

  // --- Shared UI state ---
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId);
  });

  const [chartWindow, setChartWindow] = useState<string>(() => {
    if (typeof window === 'undefined') return '1';
    const stored = window.localStorage.getItem(STORAGE_KEYS.chartWindow);
    const isValid = stored ? DASHBOARD_WINDOWS.some((w) => w.value === stored) : false;
    return isValid ? (stored as string) : '1';
  });

  const [activeTab, setActiveTab] = useState<string | null>(() => {
    if (typeof window === 'undefined') return 'panoramica';
    const stored = window.localStorage.getItem(STORAGE_KEYS.activeTab);
    return stored && DASHBOARD_TABS.includes(stored as (typeof DASHBOARD_TABS)[number]) ? stored : 'panoramica';
  });

  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  // --- Queries ---
  const { data: portfolios = [], isLoading: portfoliosLoading, error: portfoliosError } = usePortfolios();
  const portfolioId = selectedPortfolioId ? Number(selectedPortfolioId) : null;
  const { data: targetPerformance } = useTargetPerformance(portfolioId);

  // --- Auto-select portfolio ---
  useEffect(() => {
    if (!portfolios.length) return;
    setSelectedPortfolioId((prev) => {
      const prevExists = prev ? portfolios.some((p) => String(p.id) === prev) : false;
      return prevExists ? prev : String(portfolios[0].id);
    });
  }, [portfolios]);

  // --- Persist UI state ---
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (selectedPortfolioId) {
      window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, selectedPortfolioId);
    } else {
      window.localStorage.removeItem(STORAGE_KEYS.selectedPortfolioId);
    }
  }, [selectedPortfolioId]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEYS.chartWindow, chartWindow);
  }, [chartWindow]);

  // --- Global refresh listener ---
  useEffect(() => {
    const onRefresh = async () => {
      if (!portfolioId || !Number.isFinite(portfolioId)) {
        setRefreshMessage('Seleziona un portfolio prima di aggiornare');
        return;
      }
      setRefreshError(null);
      setRefreshMessage(null);
      setRefreshing(true);
      try {
        const refreshResult = await refreshPortfolioPrices(portfolioId, 'transactions');
        const backfillResult = await backfillPortfolioDailyPrices(portfolioId, 365, 'transactions');
        await queryClient.invalidateQueries();
        setRefreshMessage(
          `Aggiornati prezzi: ${refreshResult.refreshed_assets}/${refreshResult.requested_assets}, storico: ${backfillResult.assets_refreshed}/${backfillResult.assets_requested}`,
        );
      } catch (err) {
        setRefreshError(err instanceof Error ? err.message : 'Errore durante aggiornamento prezzi');
      } finally {
        setRefreshing(false);
      }
    };
    window.addEventListener('valore365:refresh-dashboard', onRefresh);
    return () => { window.removeEventListener('valore365:refresh-dashboard', onRefresh); };
  }, [portfolioId, queryClient]);

  // --- Tab navigation ---
  const handleTabChange = (tab: string | null) => {
    setActiveTab(tab);
    if (typeof window !== 'undefined' && tab) {
      window.localStorage.setItem(STORAGE_KEYS.activeTab, tab);
    }
  };

  // Auto-dismiss refresh message after 5s
  useEffect(() => {
    if (!refreshMessage) return;
    const timer = window.setTimeout(() => setRefreshMessage(null), 5000);
    return () => window.clearTimeout(timer);
  }, [refreshMessage]);

  const error = refreshError || (portfoliosError instanceof Error ? portfoliosError.message : null);
  const mobileTabItems = [
    { value: 'panoramica', label: 'Home', icon: IconChartPie },
    { value: 'posizioni', label: 'Posizioni', icon: IconList },
    ...(ENABLE_TARGET_ALLOCATION ? [{ value: 'analisi', label: 'Analisi', icon: IconChartBar }] : []),
    { value: 'mercati', label: 'Mercati', icon: IconWorld },
    { value: 'performance', label: 'Perf.', icon: IconPercentage },
  ];

  const handleRefresh = () => {
    window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard'));
  };

  return (
    <Box
      style={{
        padding: 'var(--mantine-spacing-sm)',
        paddingBottom: isMobile ? 104 : undefined,
        background: isMobile ? 'linear-gradient(180deg, #eef6f4 0%, #f8fafc 22%, transparent 42%)' : undefined,
        minHeight: '100%',
      }}
    >
      {isMobile ? (
        <DashboardMobileHeader
          portfolios={portfolios}
          selectedPortfolioId={selectedPortfolioId}
          onSelectPortfolio={(nextValue) => setSelectedPortfolioId(nextValue)}
          portfoliosLoading={portfoliosLoading}
          refreshing={refreshing}
          refreshMessage={refreshMessage}
          lastUpdatedAt={!error && ENABLE_TARGET_ALLOCATION && !refreshing && !refreshMessage ? (targetPerformance?.last_updated_at ?? null) : null}
          onRefresh={handleRefresh}
        />
      ) : (
        <Group justify="space-between" mb="md" align="flex-end" wrap="wrap" gap="xs">
          <Title order={2} fw={700}>Dashboard</Title>
          <PortfolioSwitcher
            portfolios={portfolios}
            value={selectedPortfolioId}
            onChange={(nextValue) => setSelectedPortfolioId(nextValue)}
            loading={portfoliosLoading}
            onOpenPortfolio={() => navigate('/portfolio')}
            style={{ width: '100%', maxWidth: 360 }}
          />
        </Group>
      )}

      {error && <Alert color="red" mb="md">{error}</Alert>}

      {!isMobile && (
      <Group mb="md" gap="xs" wrap="wrap">
        {refreshing && (
          <Badge variant="light" color="blue" size="lg" leftSection={<Loader size={12} />}>
            Aggiornamento in corso...
          </Badge>
        )}
        {refreshMessage && (
          <Badge variant="light" color="teal" size="lg">
            {refreshMessage}
          </Badge>
        )}
        {!error && ENABLE_TARGET_ALLOCATION && targetPerformance?.last_updated_at && !refreshing && !refreshMessage && (
          <Badge variant="dot" color="green" size="lg">
            Aggiornato: {formatDateTime(targetPerformance.last_updated_at)}
          </Badge>
        )}
        {portfoliosLoading && (
          <Badge variant="light" color="gray" size="lg" leftSection={<Loader size={12} />}>
            Caricamento portafogli...
          </Badge>
        )}
      </Group>
      )}

      <Tabs value={activeTab} onChange={handleTabChange} variant="default">
        {!isMobile && (
          <Tabs.List
            mb="md"
            style={{
              flexWrap: 'nowrap',
              overflowX: 'auto',
              overflowY: 'hidden',
              WebkitOverflowScrolling: 'touch',
              scrollbarWidth: 'none',
              paddingBottom: 0,
              gap: 0,
            }}
          >
            <Tabs.Tab value="panoramica" leftSection={<IconChartPie size={16} />}>
              <Text span>Panoramica</Text>
            </Tabs.Tab>
            <Tabs.Tab value="posizioni" leftSection={<IconList size={16} />}>
              <Text span>Posizioni</Text>
            </Tabs.Tab>
            {ENABLE_TARGET_ALLOCATION && (
              <Tabs.Tab value="analisi" leftSection={<IconChartBar size={16} />}>
                <Text span>Analisi</Text>
              </Tabs.Tab>
            )}
            <Tabs.Tab
              value="mercati"
              leftSection={<IconWorld size={16} />}
            >
              <Text span>Mercati</Text>
            </Tabs.Tab>
            <Tabs.Tab
              value="performance"
              leftSection={<IconPercentage size={16} />}
            >
              <Text span>Performance</Text>
            </Tabs.Tab>
          </Tabs.List>
        )}

        <div>
          <Tabs.Panel value="panoramica">
            <PanoramicaTab portfolioId={portfolioId} chartWindow={chartWindow} setChartWindow={setChartWindow} />
          </Tabs.Panel>

          <Tabs.Panel value="posizioni">
            <PosizioniTab portfolioId={portfolioId} />
          </Tabs.Panel>

          {ENABLE_TARGET_ALLOCATION && (
            <Tabs.Panel value="analisi">
              <AnalisiTab portfolioId={portfolioId} chartWindow={chartWindow} setChartWindow={setChartWindow} />
            </Tabs.Panel>
          )}

          <Tabs.Panel value="mercati">
            <MercatiTab />
          </Tabs.Panel>

          <Tabs.Panel value="performance">
            <PerformanceMetrics portfolioId={portfolioId} />
          </Tabs.Panel>
        </div>
      </Tabs>

      {isMobile && (
        <MobileBottomNav
          items={mobileTabItems}
          value={activeTab}
          onChange={handleTabChange}
        />
      )}
    </Box>
  );
}
