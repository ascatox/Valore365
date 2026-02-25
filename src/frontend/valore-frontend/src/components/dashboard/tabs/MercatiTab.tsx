import { useEffect } from 'react';
import { Alert, Button, Card, Group, Loader, SimpleGrid, Stack, Text, ThemeIcon } from '@mantine/core';
import { IconRefresh, IconTrendingDown, IconTrendingUp } from '@tabler/icons-react';
import { formatDateTime, formatPct, getVariationColor } from '../formatters';
import type { MarketDataState } from '../hooks/useMarketData';
import type { MarketQuoteItem } from '../../../services/api';

interface MercatiTabProps {
  marketData: MarketDataState;
  isActive: boolean;
}

const formatMarketPrice = (value: number | null) => {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  const abs = Math.abs(value);
  const decimals = abs >= 1000 ? 2 : abs >= 1 ? 2 : 4;
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  }).format(value);
};

function MarketItemCard({ item }: { item: MarketQuoteItem }) {
  const variation = item.change_pct;
  const variationColor = variation != null ? getVariationColor(variation) : 'gray';
  const isError = !!item.error;

  return (
    <Card withBorder radius="md" shadow="sm" style={{ opacity: isError ? 0.75 : 1 }}>
      <Stack gap="xs">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <div>
            <Text fw={600}>{item.name}</Text>
            <Text size="xs" c="dimmed">{item.symbol}</Text>
          </div>
          <ThemeIcon
            color={variation != null ? variationColor : 'gray'}
            variant="light"
            radius="xl"
            aria-label="Trend"
          >
            {variation != null && variation < 0 ? <IconTrendingDown size={16} /> : <IconTrendingUp size={16} />}
          </ThemeIcon>
        </Group>

        <Text fw={700} size="lg">{formatMarketPrice(item.price)}</Text>

        <Group justify="space-between" gap="xs">
          <Text size="sm" c={variationColor} fw={600}>
            {variation != null ? formatPct(variation) : 'N/D'}
          </Text>
          <Text size="xs" c="dimmed">
            {item.ts ? formatDateTime(item.ts) : 'N/D'}
          </Text>
        </Group>

        {item.error && (
          <Text size="xs" c="red">
            {item.error}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

export function MercatiTab({ marketData, isActive }: MercatiTabProps) {
  const { data, loading, error, loaded, lastUpdatedAt, fetchMarketData } = marketData;

  useEffect(() => {
    if (!isActive) return;
    void fetchMarketData();
  }, [isActive, fetchMarketData]);

  useEffect(() => {
    if (!isActive) return;
    const timer = window.setInterval(() => {
      void fetchMarketData(true);
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [isActive, fetchMarketData]);

  if (loading && !loaded) {
    return (
      <Group>
        <Loader size="sm" />
        <Text size="sm" c="dimmed">Caricamento quotazioni di mercato...</Text>
      </Group>
    );
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap" gap="xs">
        <Stack gap={0}>
          <Text size="sm" c="dimmed">
            Quotazioni live da provider finanziario (nessun dato salvato su DB)
          </Text>
          <Text size="xs" c="dimmed">
            Ultimo aggiornamento: {lastUpdatedAt ? formatDateTime(lastUpdatedAt) : 'N/D'}
          </Text>
        </Stack>
        <Button
          size="xs"
          variant="default"
          leftSection={<IconRefresh size={14} />}
          onClick={() => void fetchMarketData(true)}
          loading={loading}
        >
          Aggiorna
        </Button>
      </Group>

      {error && <Alert color="red">{error}</Alert>}

      {!loading && !data && !error && (
        <Text size="sm" c="dimmed">Apri il tab per caricare i dati di mercato.</Text>
      )}

      {data?.categories.map((category) => (
        <Card key={category.category} withBorder radius="md" p="md" shadow="sm">
          <Text fw={700} mb="md">{category.label}</Text>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
            {category.items.map((item) => (
              <MarketItemCard key={item.symbol} item={item} />
            ))}
          </SimpleGrid>
        </Card>
      ))}
    </Stack>
  );
}
