import { Badge, Grid, Group, Loader, Paper, Text } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { formatPct, formatDateTime, getVariationColor } from '../formatters';
import type { AssetMiniChartData } from '../types';

interface AssetMiniChartsGridProps {
  assets: AssetMiniChartData[];
  chartWindow: string;
  assetIntradayLoading: boolean;
}

function renderIndexTooltip(labelPrefix?: string) {
  return ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const rawValue = Number(payload[0]?.value ?? 0);
    if (!Number.isFinite(rawValue)) return null;
    const pct = ((rawValue / 100) - 1) * 100;
    return (
      <Paper withBorder p="xs" radius="sm" shadow="xs">
        <Text size="xs" c="dimmed">{labelPrefix ? `${labelPrefix} ${label}` : label}</Text>
        <Text size="sm" fw={600}>Indice: {rawValue.toFixed(2)}</Text>
        <Text size="sm" c={getVariationColor(pct)} fw={500}>Variazione: {formatPct(pct)}</Text>
      </Paper>
    );
  };
}

export function AssetMiniChartsGrid({ assets, chartWindow, assetIntradayLoading }: AssetMiniChartsGridProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const gridColor = isDark ? theme.colors.dark[4] : '#e9ecef';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  if (!assets.length) {
    return <Text c="dimmed" size="sm">Nessun dato per i titoli del portafoglio</Text>;
  }

  return (
    <Grid gutter="md">
      {assets.map((asset) => (
        <Grid.Col key={asset.asset_id} span={{ base: 12, lg: 6 }}>
          <Paper withBorder radius="md" p="sm">
            <Group justify="space-between" mb="xs" align="flex-start">
              <div>
                <Text fw={600} size="sm">{asset.symbol}</Text>
                <Text size="xs" c="dimmed">{asset.name}</Text>
                <Text size="xs" c="dimmed">
                  Peso {asset.weight_pct.toFixed(2)}% • {formatDateTime(asset.as_of)}
                </Text>
              </div>
              <Badge color={getVariationColor(asset.return_pct)} variant="light">
                {formatPct(asset.return_pct)}
              </Badge>
            </Group>
            <div style={{ height: 180 }}>
              {assetIntradayLoading && chartWindow === '1' ? (
                <Group h="100%" justify="center">
                  <Loader size="xs" />
                  <Text c="dimmed" size="xs">Intraday...</Text>
                </Group>
              ) : asset.chart.length === 0 ? (
                <Group h="100%" justify="center">
                  <Text c="dimmed" size="xs">Nessuno storico</Text>
                </Group>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={asset.chart} syncId="portfolio-target-series">
                    <defs>
                      <linearGradient id={`asset-${asset.asset_id}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#339af0" stopOpacity={0.22} />
                        <stop offset="95%" stopColor="#339af0" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
                    <XAxis
                      dataKey={chartWindow === '1' ? 'time' : 'date'}
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: tickColor, fontSize: 11 }}
                      minTickGap={24}
                    />
                    <YAxis hide domain={['auto', 'auto']} />
                    <Tooltip content={renderIndexTooltip(chartWindow === '1' ? 'Ora' : 'Data')} />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="#1c7ed6"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill={`url(#asset-${asset.asset_id})`}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </Paper>
        </Grid.Col>
      ))}
    </Grid>
  );
}
