import { useEffect, useState } from 'react';
import {
  ActionIcon,
  Alert,
  Badge,
  Group,
  Loader,
  Tabs,
  Text,
} from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import { useQueryClient } from '@tanstack/react-query';
import { IconChartPie, IconList, IconChartBar, IconWorld, IconPercentage, IconRobot } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { DashboardMobileHeader } from '../components/mobile/DashboardMobileHeader';
import { MobileBottomNav } from '../components/mobile/MobileBottomNav';
import { usePortfolioSummary, usePortfolios, useTargetPerformance } from '../components/dashboard/hooks/queries';
import { PanoramicaTab } from '../components/dashboard/tabs/PanoramicaTab';
import { PosizioniTab } from '../components/dashboard/tabs/PosizioniTab';
import { AnalisiTab } from '../components/dashboard/tabs/AnalisiTab';
import { MercatiTab } from '../components/dashboard/tabs/MercatiTab';
import { PerformanceMetrics } from '../components/dashboard/analysis/PerformanceMetrics';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher';
import { formatDateTime } from '../components/dashboard/formatters';
import { DASHBOARD_WINDOWS, STORAGE_KEYS } from '../components/dashboard/constants';

import { refreshPortfolioPrices, backfillPortfolioDailyPrices, getCopilotStatus } from '../services/api';
import { CopilotChat } from '../components/copilot/CopilotChat';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';

export function DashboardPage() {
  const DASHBOARD_TABS = ['panoramica', 'posizioni', 'analisi', 'mercati', 'performance'] as const;
  const DASHBOARD_QUERY_PREFIXES = new Set([
    'portfolio-summary',
    'portfolio-positions',
    'portfolio-allocation',
    'portfolio-timeseries',
    'portfolio-data-coverage',
    'portfolio-health',
    'portfolio-xray',
    'target-allocation',
    'target-performance',
    'target-asset-performance',
    'intraday-target-performance',
    'asset-intraday-target-performance',
    'portfolio-intraday-timeseries',
    'intraday-detail',
    'gain-timeseries',
    'performance-summary',
    'twr-timeseries',
    'mwr-timeseries',
    'benchmark-prices',
    'benchmarks',
    'market-quotes',
    'market-news',
    'portfolios',
  ]);

  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const isMobile = useMediaQuery('(max-width: 48em)');

  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId);
  });

  const [chartWindow, setChartWindow] = useState<string>(() => {
    if (typeof window === 'undefined') return '1';
    const stored = window.localStorage.getItem(STORAGE_KEYS.chartWindow);
    const isValid = stored ? DASHBOARD_WINDOWS.some((w) => w.value === stored) : false;
    return isValid ? stored : '1';
  });

  const [activeTab, setActiveTab] = useState<string | null>(() => {
    if (typeof window === 'undefined') return 'panoramica';
    const stored = window.localStorage.getItem(STORAGE_KEYS.activeTab);
    return stored && DASHBOARD_TABS.includes(stored as (typeof DASHBOARD_TABS)[number]) ? stored : 'panoramica';
  });

  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);

  const [copilotOpened, { open: openCopilot, close: closeCopilot }] = useDisclosure(false);
  const [copilotAvailable, setCopilotAvailable] = useState(false);

  useEffect(() => {
    getCopilotStatus().then((s) => setCopilotAvailable(s.available)).catch(() => {});
  }, []);

  const { data: portfolios = [], isLoading: portfoliosLoading, error: portfoliosError } = usePortfolios();
  const portfolioId = selectedPortfolioId ? Number(selectedPortfolioId) : null;
  const { data: summary } = usePortfolioSummary(portfolioId);
  const { data: targetPerformance } = useTargetPerformance(portfolioId);

  useEffect(() => {
    if (!portfolios.length) return;
    setSelectedPortfolioId((prev) => {
      const prevExists = prev ? portfolios.some((p) => String(p.id) === prev) : false;
      return prevExists ? prev : String(portfolios[0].id);
    });
  }, [portfolios]);

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
        const refreshResult = await refreshPortfolioPrices(portfolioId, 'all');
        const backfillResult = await backfillPortfolioDailyPrices(portfolioId, 365, 'all');

        await queryClient.resetQueries({
          predicate: (query) => {
            const [prefix, queryPortfolioId] = query.queryKey as [string | undefined, unknown];
            if (!prefix || !DASHBOARD_QUERY_PREFIXES.has(prefix)) return false;
            if (queryPortfolioId == null) return true;
            return queryPortfolioId === portfolioId;
          },
        });

        await queryClient.refetchQueries({
          predicate: (query) => {
            const [prefix, queryPortfolioId] = query.queryKey as [string | undefined, unknown];
            if (!prefix || !DASHBOARD_QUERY_PREFIXES.has(prefix)) return false;
            if (queryPortfolioId == null) return true;
            return queryPortfolioId === portfolioId;
          },
          type: 'active',
        });

        setRefreshVersion((current) => current + 1);
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
    return () => {
      window.removeEventListener('valore365:refresh-dashboard', onRefresh);
    };
  }, [portfolioId, queryClient]);

  const handleTabChange = (tab: string | null) => {
    setActiveTab(tab);
    if (typeof window !== 'undefined' && tab) {
      window.localStorage.setItem(STORAGE_KEYS.activeTab, tab);
    }
  };

  useEffect(() => {
    if (!refreshMessage) return;
    const timer = window.setTimeout(() => setRefreshMessage(null), 5000);
    return () => window.clearTimeout(timer);
  }, [refreshMessage]);

  const error = refreshError || (portfoliosError instanceof Error ? portfoliosError.message : null);
  const mobileTabItems = [
    { value: 'panoramica', label: 'Home', icon: IconChartPie },
    { value: 'posizioni', label: 'Posizioni', icon: IconList },
    { value: 'analisi', label: 'Analisi', icon: IconChartBar },
    { value: 'mercati', label: 'Mercati', icon: IconWorld },
    { value: 'performance', label: 'Perf.', icon: IconPercentage },
  ];

  const handleRefresh = () => {
    window.dispatchEvent(new CustomEvent('valore365:refresh-dashboard'));
  };

  return (
    <PageLayout mobileBottomPadding={isMobile ? 'calc(104px + var(--safe-area-bottom))' : undefined}>
      {isMobile ? (
        <>
          <PageHeader
            eyebrow="Vista operativa del patrimonio"
            title="Dashboard"
            description="Monitoraggio quotidiano, performance e mercati in un unico punto."
          />
          <DashboardMobileHeader
            portfolios={portfolios}
            selectedPortfolioId={selectedPortfolioId}
            selectedPortfolioCashBalance={summary?.cash_balance ?? null}
            onSelectPortfolio={(nextValue) => setSelectedPortfolioId(nextValue)}
            portfoliosLoading={portfoliosLoading}
            refreshing={refreshing}
            refreshMessage={refreshMessage}
            lastUpdatedAt={!error && !refreshing && !refreshMessage ? (targetPerformance?.last_updated_at ?? null) : null}
          />
        </>
      ) : (
        <PageHeader
          eyebrow="Vista operativa del patrimonio"
          title="Dashboard"
          description="Monitoraggio quotidiano, performance e mercati in un unico punto."
          actions={(
            <PortfolioSwitcher
              portfolios={portfolios}
              value={selectedPortfolioId}
              selectedPortfolioCashBalance={summary?.cash_balance ?? null}
              onChange={(nextValue) => setSelectedPortfolioId(nextValue)}
              loading={portfoliosLoading}
              onOpenPortfolio={() => navigate('/portfolio')}
              style={{ width: '100%', maxWidth: 360 }}
            />
          )}
        />
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
          {!error && targetPerformance?.last_updated_at && !refreshing && !refreshMessage && (
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

      <Tabs
        key={`dashboard-refresh-${portfolioId ?? 'none'}-${refreshVersion}`}
        value={activeTab}
        onChange={handleTabChange}
        variant="default"
      >
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
            <Tabs.Tab value="analisi" leftSection={<IconChartBar size={16} />}>
              <Text span>Analisi</Text>
            </Tabs.Tab>
            <Tabs.Tab value="mercati" leftSection={<IconWorld size={16} />}>
              <Text span>Mercati</Text>
            </Tabs.Tab>
            <Tabs.Tab value="performance" leftSection={<IconPercentage size={16} />}>
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

          <Tabs.Panel value="analisi">
            <AnalisiTab portfolioId={portfolioId} chartWindow={chartWindow} setChartWindow={setChartWindow} />
          </Tabs.Panel>

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

      {copilotAvailable && (
        <ActionIcon
          variant="filled"
          color="teal"
          size={52}
          radius="xl"
          onClick={openCopilot}
          aria-label="Apri Portfolio Copilot"
          style={{
            position: 'fixed',
            bottom: isMobile ? 'calc(80px + var(--safe-area-bottom))' : 24,
            right: 24,
            zIndex: 100,
            boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
          }}
        >
          <IconRobot size={24} />
        </ActionIcon>
      )}

      <CopilotChat
        opened={copilotOpened}
        onClose={closeCopilot}
        portfolioId={portfolioId}
        pageContext="dashboard"
      />
    </PageLayout>
  );
}
