import { useState } from 'react';
import {
  Alert,
  Group,
  Loader,
  Select,
  Tabs,
  Text,
  Title,
} from '@mantine/core';
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
  const data = useDashboardData();
  const marketData = useMarketData();
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

      <Tabs value={activeTab} onChange={handleTabChange}>
        <Tabs.List mb="md">
          <Tabs.Tab value="panoramica" leftSection={<IconChartPie size={16} />}>
            Panoramica
          </Tabs.Tab>
          <Tabs.Tab value="posizioni" leftSection={<IconList size={16} />}>
            Posizioni
          </Tabs.Tab>
          <Tabs.Tab value="analisi" leftSection={<IconChartBar size={16} />}>
            Analisi
          </Tabs.Tab>
          <Tabs.Tab value="mercati" leftSection={<IconWorld size={16} />}>
            Mercati
          </Tabs.Tab>
        </Tabs.List>

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
      </Tabs>
    </div>
  );
}
