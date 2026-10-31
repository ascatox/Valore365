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
import { IconChartPie, IconList, IconChartBar, IconWorld, IconPercentage, IconRobot } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { prefetchMarketData, usePortfolioSummary, usePortfolios, useTargetPerformance } from '../components/dashboard/hooks/queries';
import { useQueryClient } from '@tanstack/react-query';
import { useDashboardRefresh } from '../components/dashboard/hooks/useDashboardRefresh';
import { PanoramicaTab } from '../components/dashboard/tabs/PanoramicaTab';
import { PosizioniTab } from '../components/dashboard/tabs/PosizioniTab';
import { AnalisiTab } from '../components/dashboard/tabs/AnalisiTab';
import { MercatiTab } from '../components/dashboard/tabs/MercatiTab';
import { PerformanceMetrics } from '../components/dashboard/analysis/PerformanceMetrics';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher';
import { formatDateTime } from '../components/dashboard/formatters';
import { DASHBOARD_WINDOWS, SHOW_ANALISI_TAB, STORAGE_KEYS } from '../components/dashboard/constants';

import { getCopilotStatus } from '../services/api';
import { usePortfolioScope } from '../scope/PortfolioScopeContext';
import { scopePortfolioIds, singlePortfolioId } from '../scope/portfolioScope';
import { CopilotChat } from '../components/copilot/CopilotChat';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { useSwipeTabs } from '../hooks/useSwipeTabs';

const DASHBOARD_TABS: string[] = [
  'panoramica',
  'posizioni',
  ...(SHOW_ANALISI_TAB ? ['analisi'] : []),
  'mercati',
  'performance',
];

export function DashboardPage() {
  const navigate = useNavigate();
  const isMobile = useMediaQuery('(max-width: 48em)');

  // Shared scope: one portfolio or the aggregate of several, the same on every page.
  const { scope, scopeKey, isAggregate, setSingle, setScope } = usePortfolioScope();
  const singleId = singlePortfolioId(scope);

  const [chartWindow, setChartWindow] = useState<string>(() => {
    // Default to 30 days: the 1-day window is a flat line until intraday prices arrive.
    if (typeof window === 'undefined') return '30';
    const stored = window.localStorage.getItem(STORAGE_KEYS.chartWindow);
    const isValid = stored ? DASHBOARD_WINDOWS.some((w) => w.value === stored) : false;
    return isValid && stored ? stored : '30';
  });

  const [activeTab, setActiveTab] = useState<string | null>(() => {
    if (typeof window === 'undefined') return 'panoramica';
    const stored = window.localStorage.getItem(STORAGE_KEYS.activeTab);
    return stored && DASHBOARD_TABS.includes(stored) ? stored : 'panoramica';
  });

  const [copilotOpened, { open: openCopilot, close: closeCopilot }] = useDisclosure(false);
  const [copilotAvailable, setCopilotAvailable] = useState(false);

  useEffect(() => {
    getCopilotStatus().then((s) => setCopilotAvailable(s.available)).catch(() => {});
  }, []);

  const { data: portfolios = [], isLoading: portfoliosLoading, error: portfoliosError } = usePortfolios();
  const { data: summary } = usePortfolioSummary(scope);
  // Target performance is per portfolio (disabled in the aggregate view): it
  // only provides the "last updated" badge here.
  const { data: targetPerformance } = useTargetPerformance(scope);
  const { refreshing, refreshMessage, refreshError, refreshVersion } = useDashboardRefresh(scope);
  const scopeIds = scopePortfolioIds(scope);

  // Load the Mercati tab's data with the dashboard, once the portfolio summary
  // is in (so it doesn't compete with what's on screen): the tab then opens
  // with quotes, news and calendar ready instead of a spinner.
  const queryClient = useQueryClient();
  const summaryLoaded = summary != null;
  useEffect(() => {
    if (summaryLoaded) void prefetchMarketData(queryClient);
  }, [summaryLoaded, queryClient]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEYS.chartWindow, chartWindow);
  }, [chartWindow]);

  const handleTabChange = (tab: string | null) => {
    setActiveTab(tab);
    if (typeof window !== 'undefined' && tab) {
      window.localStorage.setItem(STORAGE_KEYS.activeTab, tab);
    }
  };

  const swipeRef = useSwipeTabs({ tabs: DASHBOARD_TABS, active: activeTab, onChange: handleTabChange, enabled: !!isMobile });

  const error = refreshError || (portfoliosError instanceof Error ? portfoliosError.message : null);
  const lastUpdatedAt = !error ? (targetPerformance?.last_updated_at ?? null) : null;
  // While refreshing, the spinning header icon is the progress signal.
  const mobileStatusText = refreshing
    ? null
    : refreshMessage ?? (lastUpdatedAt ? `Aggiornato ${formatDateTime(lastUpdatedAt)}` : null);
  // Mobile: text tabs at the top of the sticky header; the bottom bar is the
  // app navigation. A second Tabs instance drives the same activeTab.
  const mobileTabs = (
    <Tabs value={activeTab} onChange={handleTabChange} mt={6}>
      <Tabs.List style={{ flexWrap: 'nowrap', overflowX: 'auto', scrollbarWidth: 'none' }}>
        <Tabs.Tab value="panoramica">Panoramica</Tabs.Tab>
        <Tabs.Tab value="posizioni">Posizioni</Tabs.Tab>
        {SHOW_ANALISI_TAB && <Tabs.Tab value="analisi">Analisi</Tabs.Tab>}
        <Tabs.Tab value="mercati">Mercati</Tabs.Tab>
        <Tabs.Tab value="performance">Performance</Tabs.Tab>
      </Tabs.List>
    </Tabs>
  );

  const switcherProps = {
    portfolios,
    value: singleId != null ? String(singleId) : null,
    selectedPortfolioCashBalance: summary?.cash_balance ?? null,
    onChange: (nextValue: string) => setSingle(Number(nextValue)),
    loading: portfoliosLoading,
    onOpenPortfolio: () => navigate('/portfolio'),
    allowAggregate: true,
    scope,
    onScopeChange: setScope,
    aggregateTotalValue: isAggregate && summary ? summary.market_value + summary.cash_balance : null,
  };

  return (
    <PageLayout>
      {isMobile ? (
        <PageHeader
          title="Dashboard"
          hideMobileTitle
          mobileBelow={mobileTabs}
          actions={(
            <PortfolioSwitcher
              {...switcherProps}
            />
          )}
        />
      ) : (
        <PageHeader
          eyebrow="Vista operativa del patrimonio"
          title="Dashboard"
          description="Monitoraggio quotidiano, performance e mercati in un unico punto."
          actions={(
            <PortfolioSwitcher
              {...switcherProps}
              style={{ width: '100%', maxWidth: 360 }}
            />
          )}
        />
      )}

      {error && <Alert color="red" mb="md">{error}</Alert>}

      {/* The Panoramica hero carries this line; the other tabs need it too,
          since pull-to-refresh and auto-refresh work from any of them. */}
      {isMobile && activeTab !== 'panoramica' && mobileStatusText && (
        <Text size="xs" c="dimmed" mb="sm">{mobileStatusText}</Text>
      )}

      {!isMobile && (
        <Group mb="md" gap="xs" wrap="wrap">
          {refreshing && (
            <Badge variant="light" color="teal" size="lg" leftSection={<Loader size={12} />}>
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
        key={`dashboard-refresh-${scopeKey ?? 'none'}-${refreshVersion}`}
        value={activeTab}
        onChange={handleTabChange}
        variant="default"
        // Mantine keeps inactive panels mounted by default, so every tab's
        // queries fired on first paint: one dashboard load asked the API for
        // all five tabs at once, xray and the eight performance endpoints
        // included, whichever tab the user was actually looking at. Only the
        // visible tab should fetch; react-query's 60s staleTime serves the
        // others from cache when they are opened.
        keepMounted={false}
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
            {SHOW_ANALISI_TAB && (
              <Tabs.Tab value="analisi" leftSection={<IconChartBar size={16} />}>
                <Text span>Analisi</Text>
              </Tabs.Tab>
            )}
            <Tabs.Tab value="mercati" leftSection={<IconWorld size={16} />}>
              <Text span>Mercati</Text>
            </Tabs.Tab>
            <Tabs.Tab value="performance" leftSection={<IconPercentage size={16} />}>
              <Text span>Performance</Text>
            </Tabs.Tab>
          </Tabs.List>
        )}

        <div ref={swipeRef}>
          <Tabs.Panel value="panoramica">
            <PanoramicaTab
              scope={scope}
              chartWindow={chartWindow}
              setChartWindow={setChartWindow}
              statusText={mobileStatusText}
            />
          </Tabs.Panel>

          <Tabs.Panel value="posizioni">
            <PosizioniTab scope={scope} />
          </Tabs.Panel>

          {SHOW_ANALISI_TAB && (
            <Tabs.Panel value="analisi">
              <AnalisiTab scope={scope} chartWindow={chartWindow} setChartWindow={setChartWindow} />
            </Tabs.Panel>
          )}

          <Tabs.Panel value="mercati">
            <MercatiTab />
          </Tabs.Panel>

          <Tabs.Panel value="performance">
            <PerformanceMetrics scope={scope} />
          </Tabs.Panel>
        </div>
      </Tabs>

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
            bottom: isMobile ? 'calc(92px + var(--safe-area-bottom-floating))' : 24,
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
        portfolioId={scopeIds[0] ?? null}
        portfolioIds={isAggregate ? scopeIds : undefined}
        pageContext="dashboard"
      />
    </PageLayout>
  );
}
