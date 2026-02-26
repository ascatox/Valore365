import { Badge, Card, Group, Loader, Text } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Paper } from '@mantine/core';

interface PerformanceChartProps {
  title: string;
  data: Array<{ [key: string]: any }>;
  dataKey?: string;
  xKey?: string;
  height?: number;
  color?: string;
  gradientId: string;
  loading?: boolean;
  emptyMessage?: string;
  onClick?: (state: any) => void;
  stats?: { label: string; value: string; color?: string }[];
  subtitle?: string;
  headerRight?: React.ReactNode;
  tooltipContent?: (props: any) => React.ReactNode;
}

export function PerformanceChart({
  title,
  data,
  dataKey = 'value',
  xKey = 'date',
  height = 220,
  color = '#228be6',
  gradientId,
  loading = false,
  emptyMessage = 'Nessun dato disponibile',
  onClick,
  stats,
  subtitle,
  headerRight,
  tooltipContent,
}: PerformanceChartProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');
  const gridColor = isDark ? theme.colors.dark[4] : '#e9ecef';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Group justify="space-between" mb="xs" align="center" wrap="wrap" gap="xs">
        <Group gap="xs">
          <Text fw={600} size="sm">{title}</Text>
          {stats?.map((s) => (
            <Badge
              key={s.label}
              variant="light"
              color={s.color ?? 'blue'}
              size={isMobile ? 'lg' : 'md'}
              styles={{
                root: {
                  fontSize: isMobile ? 14 : 13,
                  fontWeight: 600,
                  paddingInline: isMobile ? 12 : 10,
                  height: isMobile ? 32 : 28,
                },
              }}
            >
              {s.label} {s.value}
            </Badge>
          ))}
        </Group>
        {headerRight}
      </Group>
      {subtitle && <Text size="xs" c="dimmed" mb="sm">{subtitle}</Text>}
      <div style={{ height }}>
        {loading ? (
          <Group h="100%" justify="center">
            <Loader size="sm" />
            <Text c="dimmed" size="sm">Caricamento...</Text>
          </Group>
        ) : data.length === 0 ? (
          <Group h="100%" justify="center">
            <Text c="dimmed" size="sm">{emptyMessage}</Text>
          </Group>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} onClick={onClick}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.24} />
                  <stop offset="95%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
              <XAxis dataKey={xKey} axisLine={false} tickLine={false} tick={{ fill: tickColor, fontSize: 12 }} />
              <YAxis hide domain={['auto', 'auto']} />
              {tooltipContent ? (
                <Tooltip content={tooltipContent} />
              ) : (
                <Tooltip
                  content={({ active, payload, label }: any) => {
                    if (!active || !payload?.length) return null;
                    const rawValue = Number(payload[0]?.value ?? 0);
                    if (!Number.isFinite(rawValue)) return null;
                    return (
                      <Paper withBorder p="xs" radius="sm" shadow="xs">
                        <Text size="xs" c="dimmed">{label}</Text>
                        <Text size="sm" fw={600}>{rawValue.toFixed(2)}</Text>
                      </Paper>
                    );
                  }}
                />
              )}
              <Area
                type="monotone"
                dataKey={dataKey}
                stroke={color}
                strokeWidth={2.5}
                fillOpacity={1}
                fill={`url(#${gradientId})`}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
