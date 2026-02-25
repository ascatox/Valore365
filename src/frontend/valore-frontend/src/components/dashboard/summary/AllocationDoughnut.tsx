import { Badge, Card, Group, Text } from '@mantine/core';
import { useComputedColorScheme } from '@mantine/core';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { Paper } from '@mantine/core';
import { ALLOCATION_COLORS } from '../constants';
import type { AllocationDoughnutItem } from '../types';

interface AllocationDoughnutProps {
  title: string;
  data: AllocationDoughnutItem[];
  height?: number;
  centerLabel?: string;
}

export function AllocationDoughnut({ title, data, height = 240, centerLabel }: AllocationDoughnutProps) {
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  if (!data.length) {
    return (
      <Card withBorder radius="md" p="md" shadow="sm">
        <Text fw={600} size="sm" mb="sm">{title}</Text>
        <Group h={height} justify="center">
          <Text c="dimmed" size="sm">Nessun dato disponibile</Text>
        </Group>
      </Card>
    );
  }

  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Text fw={600} size="sm" mb="sm">{title}</Text>
      <div style={{ height, position: 'relative' }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={80}
              paddingAngle={2}
              dataKey="value"
              nameKey="name"
            >
              {data.map((_, index) => (
                <Cell key={index} fill={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }: any) => {
                if (!active || !payload?.length) return null;
                const entry = payload[0];
                return (
                  <Paper withBorder p="xs" radius="sm" shadow="xs">
                    <Text size="xs" fw={600}>{entry.name}</Text>
                    <Text size="xs" c="dimmed">{Number(entry.value).toFixed(2)}%</Text>
                  </Paper>
                );
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        {centerLabel && (
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            textAlign: 'center',
            pointerEvents: 'none',
          }}>
            <Text fw={700} size="lg" c={isDark ? 'white' : 'dark'}>{centerLabel}</Text>
          </div>
        )}
      </div>
      <Group justify="center" mt="xs" gap="xs" wrap="wrap">
        {data.slice(0, 6).map((item, index) => (
          <Badge
            key={item.name}
            size="sm"
            variant="dot"
            styles={{ root: { '--badge-dot-color': ALLOCATION_COLORS[index % ALLOCATION_COLORS.length] } }}
          >
            {item.name}
          </Badge>
        ))}
      </Group>
    </Card>
  );
}
