import { Group, Paper, Text, ThemeIcon } from '@mantine/core';
import type { KpiStatCardProps } from '../types';
import { MiniGauge } from './MiniGauge';

export function KpiStatCard({ label, value, color, icon: Icon, iconColor, gaugeValue }: KpiStatCardProps) {
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
      <Group justify="space-between" align="flex-end" wrap="nowrap">
        <Text fw={700} size="lg" c={color ?? undefined}>{value}</Text>
        {gaugeValue != null && <MiniGauge value={gaugeValue} size={48} />}
      </Group>
    </Paper>
  );
}
