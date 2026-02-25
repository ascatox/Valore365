import { Group, Paper, Text, ThemeIcon } from '@mantine/core';
import type { KpiStatCardProps } from '../types';

export function KpiStatCard({ label, value, color, icon: Icon, iconColor }: KpiStatCardProps) {
  return (
    <Paper withBorder p="sm" radius="md">
      <Group justify="space-between" mb={4}>
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{label}</Text>
        {Icon && (
          <ThemeIcon color={iconColor ?? 'blue'} variant="light" size="sm" radius="md">
            <Icon size={14} />
          </ThemeIcon>
        )}
      </Group>
      <Text fw={700} size="lg" c={color ?? undefined}>{value}</Text>
    </Paper>
  );
}
