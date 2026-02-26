import { Badge, Card, Grid, Group, Text } from '@mantine/core';
import { IconArrowUpRight, IconArrowDownRight } from '@tabler/icons-react';
import { formatPct, formatShortDate, getVariationColor } from '../formatters';
import type { PerformerItem } from '../types';

interface BestWorstCardsProps {
  best: PerformerItem[];
  worst: PerformerItem[];
  periodLabel?: string;
}

function PerformerList({
  items,
  title,
  type,
  periodLabel,
}: {
  items: PerformerItem[];
  title: string;
  type: 'best' | 'worst';
  periodLabel?: string;
}) {
  const Icon = type === 'best' ? IconArrowUpRight : IconArrowDownRight;
  const headerColor = type === 'best' ? 'green' : 'red';

  return (
    <Card withBorder radius="md" p="md" shadow="sm" h="100%">
      <Group gap="xs" mb="sm">
        <Icon size={20} color={headerColor === 'green' ? '#16a34a' : '#dc2626'} />
        <Text fw={700} size="md">{title}</Text>
      </Group>
      {periodLabel && (
        <Text size="xs" c="dimmed" mb="sm">Intervallo: {periodLabel}</Text>
      )}
      {items.length === 0 ? (
        <Text c="dimmed" size="sm">Nessun dato</Text>
      ) : (
        items.map((item) => (
          <Group key={item.asset_id} justify="space-between" mb="xs">
            <div>
              <Text size="sm" fw={500}>{item.symbol}</Text>
              <Text size="sm" c="dimmed" lineClamp={1}>{item.name}</Text>
            </div>
            <div style={{ textAlign: 'right' }}>
              <Badge color={getVariationColor(item.return_pct)} variant="light" size="sm">
                {formatPct(item.return_pct)}
              </Badge>
              {item.as_of && (
                <Text size="xs" c="dimmed">{formatShortDate(item.as_of)}</Text>
              )}
            </div>
          </Group>
        ))
      )}
    </Card>
  );
}

export function BestWorstCards({ best, worst, periodLabel }: BestWorstCardsProps) {
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, sm: 6 }}>
        <PerformerList items={best} title="Migliori" type="best" periodLabel={periodLabel} />
      </Grid.Col>
      <Grid.Col span={{ base: 12, sm: 6 }}>
        <PerformerList items={worst} title="Peggiori" type="worst" periodLabel={periodLabel} />
      </Grid.Col>
    </Grid>
  );
}
