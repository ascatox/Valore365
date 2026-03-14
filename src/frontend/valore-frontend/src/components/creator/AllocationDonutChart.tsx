import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { Text, Stack } from '@mantine/core';
import type { AllocationSlot } from './types';

interface AllocationDonutChartProps {
  slots: AllocationSlot[];
  size?: number;
}

export function AllocationDonutChart({ slots, size = 180 }: AllocationDonutChartProps) {
  return (
    <ResponsiveContainer width="100%" height={size}>
      <PieChart>
        <Pie
          data={slots}
          dataKey="weight"
          nameKey="label"
          cx="50%"
          cy="50%"
          innerRadius={size * 0.32}
          outerRadius={size * 0.46}
          paddingAngle={2}
          strokeWidth={0}
        >
          {slots.map((slot) => (
            <Cell key={slot.label} fill={slot.color} />
          ))}
        </Pie>
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.[0]) return null;
            const d = payload[0].payload as AllocationSlot;
            return (
              <Stack
                gap={2}
                p="xs"
                style={{
                  background: 'var(--mantine-color-body)',
                  border: '1px solid var(--mantine-color-default-border)',
                  borderRadius: 8,
                }}
              >
                <Text size="sm" fw={600}>{d.label}</Text>
                <Text size="sm" c="dimmed">{d.weight} %</Text>
              </Stack>
            );
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
