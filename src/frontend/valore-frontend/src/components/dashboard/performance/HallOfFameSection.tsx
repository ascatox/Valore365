import { Card, Group, Loader, SimpleGrid, Stack, Text } from '@mantine/core';
import { formatPct, getVariationColor } from '../formatters';

function RankedListCard({
  title,
  items,
}: {
  title: string;
  items: Array<{ label: string; return_pct: number }>;
}) {
  return (
    <Card withBorder radius="md" p="md">
      <Text fw={600} mb="sm">{title}</Text>
      <Stack gap="xs">
        {items.length === 0 ? (
          <Text size="sm" c="dimmed">Dati insufficienti</Text>
        ) : items.map((item, index) => (
          <Group key={`${title}-${item.label}-${index}`} justify="space-between" gap="xs">
            <Text size="sm">{item.label}</Text>
            <Text size="sm" fw={700} c={getVariationColor(item.return_pct)}>
              {formatPct(item.return_pct)}
            </Text>
          </Group>
        ))}
      </Stack>
    </Card>
  );
}

interface HallOfFameData {
  best_months: Array<{ label: string; return_pct: number }>;
  worst_months: Array<{ label: string; return_pct: number }>;
  best_years: Array<{ label: string; return_pct: number }>;
  worst_years: Array<{ label: string; return_pct: number }>;
}

interface HallOfFameSectionProps {
  hallOfFame: HallOfFameData | undefined;
  loading: boolean;
}

export function HallOfFameSection({ hallOfFame, loading }: HallOfFameSectionProps) {
  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Group justify="space-between" align="center" mb="sm" wrap="wrap" gap="xs">
        <Text fw={600}>Hall of Fame</Text>
        {loading && (
          <Group gap="xs">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">Caricamento classifiche...</Text>
          </Group>
        )}
      </Group>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
        <RankedListCard title="Mesi migliori" items={hallOfFame?.best_months ?? []} />
        <RankedListCard title="Mesi peggiori" items={hallOfFame?.worst_months ?? []} />
        <RankedListCard title="Anni migliori" items={hallOfFame?.best_years ?? []} />
        <RankedListCard title="Anni peggiori" items={hallOfFame?.worst_years ?? []} />
      </SimpleGrid>
    </Card>
  );
}
