import { Badge, Card, Group, Loader, Text } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Paper } from '@mantine/core';
import { formatNum } from '../formatters';

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
  const resolvedHeight = isMobile ? Math.max(height, 300) : height;

  return (
    <Card
      withBorder
      radius={isMobile ? 'xl' : 'md'}
      p={isMobile ? 'lg' : 'md'}
      shadow="sm"
      style={isMobile ? {
        background: isDark
          ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
          : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
        boxShadow: isDark ? '0 18px 38px rgba(0, 0, 0, 0.28)' : '0 18px 38px rgba(15, 23, 42, 0.08)',
      } : undefined}
    >
      <Group justify="space-between" mb="xs" align={isMobile ? 'flex-start' : 'center'} wrap="wrap" gap="xs">
        <Group gap="xs">
          <Text fw={700} size={isMobile ? 'md' : 'sm'}>{title}</Text>
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
      <div style={{ height: resolvedHeight }}>
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
              <XAxis
                dataKey={xKey}
                axisLine={false}
                tickLine={false}
                minTickGap={isMobile ? 24 : 8}
                tick={{ fill: tickColor, fontSize: isMobile ? 11 : 12 }}
              />
              <YAxis
                domain={['auto', 'auto']}
                axisLine={false}
                tickLine={false}
                hide={isMobile}
                tick={{ fill: tickColor, fontSize: 11 }}
                width={50}
                tickFormatter={(v: number) => formatNum(v, v >= 1000 ? 0 : 1)}
              />
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
                        <Text size="sm" fw={600}>{formatNum(rawValue)}</Text>
                      </Paper>
                    );
                  }}
                />
              )}
              <Area
                type="monotone"
                dataKey={dataKey}
                stroke={color}
                strokeWidth={isMobile ? 3 : 2.5}
                fillOpacity={1}
                fill={`url(#${gradientId})`}
                activeDot={{ r: isMobile ? 6 : 4, strokeWidth: 0 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
