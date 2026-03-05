import { useState } from 'react';
import { Badge, Card, Grid, Group, Text, Tooltip, UnstyledButton } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconArrowUpRight, IconArrowDownRight, IconInfoCircle } from '@tabler/icons-react';
import { formatPct, formatShortDate, getVariationColor } from '../formatters';
import type { PerformerItem } from '../types';
import { AssetInfoModal } from '../holdings/AssetInfoModal';

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
  onInfoClick,
}: {
  items: PerformerItem[];
  title: string;
  type: 'best' | 'worst';
  periodLabel?: string;
  onInfoClick?: (assetId: number, symbol: string) => void;
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
            <Group gap={6} wrap="nowrap">
              <div>
                <Text size="sm" fw={500}>{item.symbol}</Text>
                <Text size="sm" c="dimmed" lineClamp={1}>{item.name}</Text>
              </div>
              {onInfoClick && (
                <Tooltip label="Dettaglio asset" withArrow>
                  <UnstyledButton onClick={() => onInfoClick(item.asset_id, item.symbol)}>
                    <IconInfoCircle size={16} stroke={1.5} style={{ opacity: 0.5 }} />
                  </UnstyledButton>
                </Tooltip>
              )}
            </Group>
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
  const [infoModal, setInfoModal] = useState<{ assetId: number; symbol: string } | null>(null);
  const isMobile = useMediaQuery('(max-width: 48em)');

  const handleInfoClick = isMobile ? undefined : (assetId: number, symbol: string) => {
    setInfoModal({ assetId, symbol });
  };

  return (
    <>
      {!isMobile && infoModal && (
        <AssetInfoModal
          assetId={infoModal.assetId}
          symbol={infoModal.symbol}
          opened={!!infoModal}
          onClose={() => setInfoModal(null)}
        />
      )}
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, sm: 6 }}>
          <PerformerList items={best} title="Migliori" type="best" periodLabel={periodLabel} onInfoClick={handleInfoClick} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 6 }}>
          <PerformerList items={worst} title="Peggiori" type="worst" periodLabel={periodLabel} onInfoClick={handleInfoClick} />
        </Grid.Col>
      </Grid>
    </>
  );
}
