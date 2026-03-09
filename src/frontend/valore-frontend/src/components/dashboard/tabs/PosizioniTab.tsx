import { useMemo } from 'react';
import { Badge, Card, Group, Loader, SimpleGrid, Stack, Text } from '@mantine/core';
import { HoldingsTable } from '../holdings/HoldingsTable';
import { AllocationDoughnut } from '../summary/AllocationDoughnut';
import { usePortfolioSummary, usePortfolioPositions, useTargetAllocation } from '../hooks/queries';
import type { AllocationDoughnutItem } from '../types';

const ASSET_TYPE_LABELS: Record<string, string> = {
  stock: 'Azioni',
  etf: 'ETF',
  crypto: 'Crypto',
  bond: 'Obbligazioni',
  cash: 'Liquidità',
  fund: 'Fondi',
};

interface PosizioniTabProps {
  portfolioId: number | null;
}

export function PosizioniTab({ portfolioId }: PosizioniTabProps) {
  const { data: summary } = usePortfolioSummary(portfolioId);
  const { data: positions = [], isLoading } = usePortfolioPositions(portfolioId);
  const { data: targetAllocation = [] } = useTargetAllocation(portfolioId);
  const currency = summary?.base_currency ?? 'EUR';

  const targetMap = useMemo(() => {
    const map = new Map<number, number>();
    for (const item of targetAllocation) map.set(item.asset_id, item.weight_pct);
    return map;
  }, [targetAllocation]);

  const allocationByType = useMemo<AllocationDoughnutItem[]>(() => {
    const grouped = new Map<string, number>();
    for (const p of positions) {
      const type = p.asset_type || 'stock';
      grouped.set(type, (grouped.get(type) ?? 0) + p.weight);
    }
    return Array.from(grouped.entries())
      .map(([type, weight]) => ({
        name: ASSET_TYPE_LABELS[type] ?? type,
        value: Math.round(weight * 100) / 100,
      }))
      .sort((a, b) => b.value - a.value);
  }, [positions]);

  const allocationByAsset = useMemo<AllocationDoughnutItem[]>(() => {
    const sorted = [...positions].sort((a, b) => b.weight - a.weight);
    const top = sorted.slice(0, 8);
    const rest = sorted.slice(8);
    const items: AllocationDoughnutItem[] = top.map((p) => ({
      name: p.symbol,
      value: Math.round(p.weight * 100) / 100,
      asset_id: p.asset_id,
    }));
    const otherWeight = rest.reduce((s, p) => s + p.weight, 0);
    if (otherWeight > 0) {
      items.push({ name: 'Altro', value: Math.round(otherWeight * 100) / 100 });
    }
    return items;
  }, [positions]);

  if (isLoading) {
    return (
      <Group>
        <Loader size="sm" />
        <Text size="sm" c="dimmed">Caricamento posizioni...</Text>
      </Group>
    );
  }

  return (
    <Stack gap="md">
      <Card withBorder radius="md" p="md" shadow="sm">
        <Group justify="space-between" mb="md">
          <Text fw={600} size="sm">Posizioni correnti</Text>
          <Badge variant="light">{positions.length} posizioni</Badge>
        </Group>
        <HoldingsTable positions={positions} currency={currency} summary={summary ?? null} targetMap={targetMap} />
      </Card>

      {positions.length > 0 && (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          <AllocationDoughnut
            title="Allocazione per tipo"
            data={allocationByType}
            centerLabel={`${positions.length}`}
          />
          <AllocationDoughnut
            title="Allocazione per titolo"
            data={allocationByAsset}
            centerLabel={currency}
          />
        </SimpleGrid>
      )}
    </Stack>
  );
}
