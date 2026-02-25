import { Badge, Card, Group, Text } from '@mantine/core';
import { HoldingsTable } from '../holdings/HoldingsTable';
import type { DashboardData } from '../types';

interface PosizioniTabProps {
  data: DashboardData;
}

export function PosizioniTab({ data }: PosizioniTabProps) {
  const { portfolioPositions, portfolioSummary, mvpCurrency } = data;

  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Group justify="space-between" mb="md">
        <Text fw={600} size="sm">Posizioni correnti</Text>
        <Badge variant="light">{portfolioPositions.length} posizioni</Badge>
      </Group>
      <HoldingsTable positions={portfolioPositions} currency={mvpCurrency} summary={portfolioSummary} />
    </Card>
  );
}
