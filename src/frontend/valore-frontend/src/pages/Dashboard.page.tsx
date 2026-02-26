import { useRef, useState, type TouchEvent } from 'react';
import {
  Alert,
  Group,
  Loader,
  Select,
  Tabs,
  Text,
  Title,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconChartPie, IconList, IconChartBar, IconWorld } from '@tabler/icons-react';
import { useDashboardData } from '../components/dashboard/hooks/useDashboardData';
import { useMarketData } from '../components/dashboard/hooks/useMarketData';
import { PanoramicaTab } from '../components/dashboard/tabs/PanoramicaTab';
import { PosizioniTab } from '../components/dashboard/tabs/PosizioniTab';
import { AnalisiTab } from '../components/dashboard/tabs/AnalisiTab';
import { MercatiTab } from '../components/dashboard/tabs/MercatiTab';
import { formatDateTime } from '../components/dashboard/formatters';
import { STORAGE_KEYS } from '../components/dashboard/constants';

export function DashboardPage() {
  const DASHBOARD_TABS = ['panoramica', 'posizioni', 'analisi', 'mercati'] as const;
  const data = useDashboardData();
  const marketData = useMarketData();
  const isMobile = useMediaQuery('(max-width: 48em)');
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const {
    portfolios,
    selectedPortfolioId,
    setSelectedPortfolioId,
    loading,
    dataLoading,
    refreshing,
    error,
    refreshMessage,
    targetPerformance,
  } = data;

  const [activeTab, setActiveTab] = useState<string | null>(() => {
    if (typeof window === 'undefined') return 'panoramica';
    return window.localStorage.getItem(STORAGE_KEYS.activeTab) ?? 'panoramica';
  });

  const handleTabChange = (tab: string | null) => {
    setActiveTab(tab);
    if (typeof window !== 'undefined' && tab) {
      window.localStorage.setItem(STORAGE_KEYS.activeTab, tab);
    }
  };

  const handleTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    if (!isMobile || event.touches.length !== 1) return;
    const touch = event.touches[0];
    touchStartRef.current = { x: touch.clientX, y: touch.clientY };
  };

  const handleTouchEnd = (event: TouchEvent<HTMLDivElement>) => {
    if (!isMobile || !touchStartRef.current || event.changedTouches.length !== 1 || !activeTab) return;

    const touch = event.changedTouches[0];
    const dx = touch.clientX - touchStartRef.current.x;
    const dy = touch.clientY - touchStartRef.current.y;
    touchStartRef.current = null;

    // Only horizontal swipes with limited vertical movement should switch tabs.
    if (Math.abs(dx) < 60 || Math.abs(dx) <= Math.abs(dy) || Math.abs(dy) > 80) return;

    const currentIndex = DASHBOARD_TABS.indexOf(activeTab as (typeof DASHBOARD_TABS)[number]);
    if (currentIndex < 0) return;

    const nextIndex = dx < 0 ? currentIndex + 1 : currentIndex - 1;
    if (nextIndex < 0 || nextIndex >= DASHBOARD_TABS.length) return;

    handleTabChange(DASHBOARD_TABS[nextIndex]);
  };

  return (
    <div style={{ padding: 'var(--mantine-spacing-sm)' }}>
      <Group justify="space-between" mb="md" align="flex-end" wrap="wrap" gap="xs">
        <Title order={2} fw={700}>Dashboard</Title>
        <Select
          placeholder={loading ? 'Caricamento portafogli...' : 'Seleziona portfolio'}
          data={portfolios.map((p) => ({ value: String(p.id), label: `${p.name} (#${p.id})` }))}
          value={selectedPortfolioId}
          onChange={setSelectedPortfolioId}
          disabled={loading || portfolios.length === 0}
          style={{ width: '100%', maxWidth: 280 }}
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

      <Tabs value={activeTab} onChange={handleTabChange} variant="pills" radius="xl">
        <Tabs.List
          mb="md"
          style={isMobile ? {
            flexWrap: 'nowrap',
            overflowX: 'hidden',
            padding: 4,
            gap: '0.25rem',
            background: 'var(--mantine-color-gray-1)',
            borderRadius: 999,
          } : {
            flexWrap: 'nowrap',
            overflowX: 'auto',
            overflowY: 'hidden',
            WebkitOverflowScrolling: 'touch',
            scrollbarWidth: 'none',
            paddingBottom: 4,
            gap: '0.25rem',
          }}
        >
          <Tabs.Tab
            value="panoramica"
            leftSection={isMobile ? undefined : <IconChartPie size={16} />}
            style={isMobile ? { flex: '1 1 0', minWidth: 0, justifyContent: 'center' } : { flex: '0 0 auto' }}
          >
            {isMobile ? <IconChartPie size={20} /> : <Text span>Panoramica</Text>}
          </Tabs.Tab>
          <Tabs.Tab
            value="posizioni"
            leftSection={isMobile ? undefined : <IconList size={16} />}
            style={isMobile ? { flex: '1 1 0', minWidth: 0, justifyContent: 'center' } : { flex: '0 0 auto' }}
          >
            {isMobile ? <IconList size={20} /> : <Text span>Posizioni</Text>}
          </Tabs.Tab>
          <Tabs.Tab
            value="analisi"
            leftSection={isMobile ? undefined : <IconChartBar size={16} />}
            style={isMobile ? { flex: '1 1 0', minWidth: 0, justifyContent: 'center' } : { flex: '0 0 auto' }}
          >
            {isMobile ? <IconChartBar size={20} /> : <Text span>Analisi</Text>}
          </Tabs.Tab>
          <Tabs.Tab
            value="mercati"
            leftSection={isMobile ? undefined : <IconWorld size={16} />}
            style={isMobile ? { flex: '1 1 0', minWidth: 0, justifyContent: 'center' } : { flex: '0 0 auto' }}
          >
            {isMobile ? <IconWorld size={20} /> : <Text span>Mercati</Text>}
          </Tabs.Tab>
        </Tabs.List>

        <div onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
          <Tabs.Panel value="panoramica">
            <PanoramicaTab data={data} />
          </Tabs.Panel>

          <Tabs.Panel value="posizioni">
            <PosizioniTab data={data} />
          </Tabs.Panel>

          <Tabs.Panel value="analisi">
            <AnalisiTab data={data} />
          </Tabs.Panel>

          <Tabs.Panel value="mercati">
            <MercatiTab marketData={marketData} isActive={activeTab === 'mercati'} />
          </Tabs.Panel>
        </div>
      </Tabs>
    </div>
  );
}
