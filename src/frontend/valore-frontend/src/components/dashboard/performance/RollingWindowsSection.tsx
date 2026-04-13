import { Group, Paper, SegmentedControl, SimpleGrid, Stack, Text } from '@mantine/core';
import { formatNum, formatPct, getVariationColor } from '../formatters';
import { PerformanceChart } from '../summary/PerformanceChart';
import { formatPctPlain, ROLLING_WINDOW_OPTIONS } from './utils';
import type { RollingWindowKey } from './utils';

interface ChartPoint {
  rawDate: string;
  date: string;
  value: number;
}

interface RollingLatest {
  cagr_pct: number | null;
  volatility_pct: number | null;
  sharpe_ratio: number | null;
}

interface RollingWindowsSectionProps {
  rollingWindow: RollingWindowKey;
  onRollingWindowChange: (w: RollingWindowKey) => void;
  cagrData: ChartPoint[];
  volData: ChartPoint[];
  sharpeData: ChartPoint[];
  latest: RollingLatest | null;
  loading: boolean;
}

export function RollingWindowsSection({
  rollingWindow,
  onRollingWindowChange,
  cagrData,
  volData,
  sharpeData,
  latest,
  loading,
}: RollingWindowsSectionProps) {
  return (
    <Stack gap="md">
      <Group justify="space-between" align="center" wrap="wrap" gap="xs">
        <Text fw={600}>Rolling windows</Text>
        <SegmentedControl
          size="xs"
          value={rollingWindow}
          onChange={(value) => onRollingWindowChange((value as RollingWindowKey) ?? '12')}
          data={ROLLING_WINDOW_OPTIONS}
        />
      </Group>

      <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
        <PerformanceChart
          title={`CAGR rolling ${rollingWindow}M`}
          data={cagrData}
          gradientId="rollingCagrGradient"
          color="#2563eb"
          loading={loading}
          emptyMessage={`Servono almeno ${rollingWindow} mesi di storico`}
          subtitle="Rendimento annualizzato della finestra mobile."
          stats={latest?.cagr_pct != null ? [
            { label: 'Ultimo', value: formatPct(latest.cagr_pct), color: getVariationColor(latest.cagr_pct) },
          ] : undefined}
          tooltipContent={({ active, payload, label }: any) => {
            if (!active || !payload?.length) return null;
            const value = Number(payload[0]?.value ?? 0);
            if (!Number.isFinite(value)) return null;
            return (
              <Paper withBorder p="xs" radius="sm" shadow="xs">
                <Text size="xs" c="dimmed">{label}</Text>
                <Text size="sm" fw={600} c={getVariationColor(value)}>{formatPct(value)}</Text>
              </Paper>
            );
          }}
        />

        <PerformanceChart
          title={`Volatilità rolling ${rollingWindow}M`}
          data={volData}
          gradientId="rollingVolGradient"
          color="#f59e0b"
          loading={loading}
          emptyMessage={`Servono almeno ${rollingWindow} mesi di storico`}
          subtitle="Deviazione standard annualizzata dei rendimenti mensili."
          stats={latest?.volatility_pct != null ? [
            { label: 'Ultima', value: formatPctPlain(latest.volatility_pct), color: 'yellow' },
          ] : undefined}
          tooltipContent={({ active, payload, label }: any) => {
            if (!active || !payload?.length) return null;
            const value = Number(payload[0]?.value ?? 0);
            if (!Number.isFinite(value)) return null;
            return (
              <Paper withBorder p="xs" radius="sm" shadow="xs">
                <Text size="xs" c="dimmed">{label}</Text>
                <Text size="sm" fw={600}>{formatPctPlain(value)}</Text>
              </Paper>
            );
          }}
        />

        <PerformanceChart
          title={`Sharpe rolling ${rollingWindow}M`}
          data={sharpeData}
          gradientId="rollingSharpeGradient"
          color="#7c3aed"
          loading={loading}
          emptyMessage={`Servono almeno ${rollingWindow} mesi di storico`}
          subtitle="Sharpe ratio con risk-free al 2%."
          stats={latest?.sharpe_ratio != null ? [
            { label: 'Ultimo', value: formatNum(latest.sharpe_ratio, 2), color: latest.sharpe_ratio >= 0 ? 'grape' : 'red' },
          ] : undefined}
          tooltipContent={({ active, payload, label }: any) => {
            if (!active || !payload?.length) return null;
            const value = Number(payload[0]?.value ?? 0);
            if (!Number.isFinite(value)) return null;
            return (
              <Paper withBorder p="xs" radius="sm" shadow="xs">
                <Text size="xs" c="dimmed">{label}</Text>
                <Text size="sm" fw={600} c={getVariationColor(value)}>{formatNum(value, 2)}</Text>
              </Paper>
            );
          }}
        />
      </SimpleGrid>
    </Stack>
  );
}
