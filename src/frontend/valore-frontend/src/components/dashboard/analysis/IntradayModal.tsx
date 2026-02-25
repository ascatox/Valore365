import { Alert, Group, Loader, Modal, Paper, SimpleGrid, Text } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { formatPct, getVariationColor } from '../formatters';
import type { IntradayChartPoint } from '../types';

interface IntradayModalProps {
  opened: boolean;
  onClose: () => void;
  dateLabel: string | null;
  loading: boolean;
  error: string | null;
  chartData: IntradayChartPoint[];
  stats: { open: number; last: number; min: number; max: number; dayPct: number } | null;
}

export function IntradayModal({ opened, onClose, dateLabel, loading, error, chartData, stats }: IntradayModalProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');
  const gridColor = isDark ? theme.colors.dark[4] : '#e0e0e0';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={dateLabel ? `Andamento intraday - ${dateLabel}` : 'Andamento intraday'}
      size="xl"
      fullScreen={isMobile ?? false}
    >
      {error && <Alert color="red" mb="md">{error}</Alert>}
      {loading && (
        <Group mb="md">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">Caricamento dati intraday...</Text>
        </Group>
      )}
      {!loading && !error && chartData.length === 0 && (
        <Alert color="yellow">Nessun dato intraday disponibile per questa giornata.</Alert>
      )}
      {!loading && !error && stats && (
        <SimpleGrid cols={{ base: 2, sm: 5 }} spacing="sm" mb="md">
          <Paper withBorder p="xs" radius="md">
            <Text size="xs" c="dimmed">Apertura</Text>
            <Text fw={600} size="sm">{stats.open.toFixed(2)}</Text>
          </Paper>
          <Paper withBorder p="xs" radius="md">
            <Text size="xs" c="dimmed">Ultimo</Text>
            <Text fw={600} size="sm">{stats.last.toFixed(2)}</Text>
          </Paper>
          <Paper withBorder p="xs" radius="md">
            <Text size="xs" c="dimmed">Min</Text>
            <Text fw={600} size="sm">{stats.min.toFixed(2)}</Text>
          </Paper>
          <Paper withBorder p="xs" radius="md">
            <Text size="xs" c="dimmed">Max</Text>
            <Text fw={600} size="sm">{stats.max.toFixed(2)}</Text>
          </Paper>
          <Paper withBorder p="xs" radius="md">
            <Text size="xs" c="dimmed">Var % giorno</Text>
            <Text fw={600} size="sm" c={getVariationColor(stats.dayPct)}>
              {formatPct(stats.dayPct)}
            </Text>
          </Paper>
        </SimpleGrid>
      )}
      {!loading && chartData.length > 0 && (
        <div style={{ height: 360 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="colorIntraday" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#12b886" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#12b886" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
              <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: tickColor, fontSize: 12 }} />
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip
                content={({ active, payload, label }: any) => {
                  if (!active || !payload?.length) return null;
                  const rawValue = Number(payload[0]?.value ?? 0);
                  if (!Number.isFinite(rawValue)) return null;
                  const pct = ((rawValue / 100) - 1) * 100;
                  return (
                    <Paper withBorder p="xs" radius="sm" shadow="xs">
                      <Text size="xs" c="dimmed">Ora {label}</Text>
                      <Text size="sm" fw={600}>Indice: {rawValue.toFixed(2)}</Text>
                      <Text size="sm" c={getVariationColor(pct)} fw={500}>Variazione: {formatPct(pct)}</Text>
                    </Paper>
                  );
                }}
              />
              <Area type="monotone" dataKey="value" stroke="#12b886" strokeWidth={2.5} fillOpacity={1} fill="url(#colorIntraday)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Modal>
  );
}
