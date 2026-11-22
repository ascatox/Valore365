import { Group, Paper, Text, ThemeIcon } from '@mantine/core';
import type { KpiStatCardProps } from '../types';

// The label may wrap onto two lines in narrow columns (tablet with sidebar):
// the icon stays beside it and the value sits at the bottom of the card, so
// values line up across the row whatever the label length.
export function KpiStatCard({ label, value, color, icon: Icon, iconColor }: KpiStatCardProps) {
  return (
    <Paper withBorder p="sm" radius="md" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: 4, containerType: 'inline-size' }}>
      <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ minWidth: 0 }}>{label}</Text>
        {Icon && (
          <ThemeIcon color={iconColor ?? 'teal'} variant="light" size="sm" radius="md" style={{ flexShrink: 0 }}>
            <Icon size={14} />
          </ThemeIcon>
        )}
      </Group>
      {/* One line always: the size follows the card width (container query
          units), up to Mantine's lg, so "+101.665,32 €" fits five columns on a
          tablet with the sidebar open. */}
      <Text fw={700} c={color ?? undefined} style={{ whiteSpace: 'nowrap', fontSize: 'clamp(0.8125rem, 11.5cqi, var(--mantine-font-size-lg))' }}>
        {value}
      </Text>
    </Paper>
  );
}
