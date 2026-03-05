import { useMemo } from 'react';
import { Badge, Card, Group, Loader, Text } from '@mantine/core';
import { HoldingsTable } from '../holdings/HoldingsTable';
import { usePortfolioSummary, usePortfolioPositions, useTargetAllocation } from '../hooks/queries';

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

  if (isLoading) {
    return (
      <Group>
        <Loader size="sm" />
        <Text size="sm" c="dimmed">Caricamento posizioni...</Text>
      </Group>
    );
  }

  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Group justify="space-between" mb="md">
        <Text fw={600} size="sm">Posizioni correnti</Text>
        <Badge variant="light">{positions.length} posizioni</Badge>
      </Group>
      <HoldingsTable positions={positions} currency={currency} summary={summary ?? null} targetMap={targetMap} />
    </Card>
  );
}
