import { Card, Paper, SimpleGrid, Stack, Text } from '@mantine/core';
import { formatMoney, formatPct, formatShortDate, getVariationColor } from '../formatters';
import { PerformanceChart } from '../summary/PerformanceChart';

interface DrawdownData {
  points: Array<{ date: string; drawdown_pct: number }>;
  max_drawdown_pct: number;
  current_drawdown_pct: number;
  peak_value: number | null;
  peak_date: string;
  max_drawdown_start: string;
  max_drawdown_end: string;
}

interface DrawdownSectionProps {
  drawdown: DrawdownData | undefined;
  chartData: Array<{ rawDate: string; date: string; value: number }>;
  loading: boolean;
  currency: string;
}

export function DrawdownSection({ drawdown, chartData, loading, currency }: DrawdownSectionProps) {
  return (
    <Stack gap="md">
      <PerformanceChart
        title="Underwater drawdown"
        data={chartData}
        gradientId="drawdownGradient"
        color="#ef4444"
        loading={loading}
        emptyMessage="Nessun drawdown disponibile"
        subtitle="Scostamento percentuale dal picco cumulato del periodo."
        stats={drawdown ? [
          { label: 'Max DD', value: formatPct(drawdown.max_drawdown_pct), color: getVariationColor(drawdown.max_drawdown_pct) },
          { label: 'Corrente', value: formatPct(drawdown.current_drawdown_pct), color: getVariationColor(drawdown.current_drawdown_pct) },
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

      {drawdown && (
        <SimpleGrid cols={{ base: 1, md: 3 }} spacing="sm">
          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Picco storico nel range</Text>
            <Text fw={700}>
              {drawdown.peak_value != null ? formatMoney(drawdown.peak_value, currency) : 'N/D'}
            </Text>
            <Text size="xs" c="dimmed">{formatShortDate(drawdown.peak_date) ?? 'Data non disponibile'}</Text>
          </Card>
          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Massimo drawdown</Text>
            <Text fw={700} c={getVariationColor(drawdown.max_drawdown_pct)}>
              {formatPct(drawdown.max_drawdown_pct)}
            </Text>
            <Text size="xs" c="dimmed">
              {formatShortDate(drawdown.max_drawdown_start) ?? 'N/D'} {'->'} {formatShortDate(drawdown.max_drawdown_end) ?? 'N/D'}
            </Text>
          </Card>
          <Card withBorder radius="md" p="sm">
            <Text size="sm" c="dimmed">Drawdown attuale</Text>
            <Text fw={700} c={getVariationColor(drawdown.current_drawdown_pct)}>
              {formatPct(drawdown.current_drawdown_pct)}
            </Text>
            <Text size="xs" c="dimmed">Dal picco più recente del periodo selezionato</Text>
          </Card>
        </SimpleGrid>
      )}
    </Stack>
  );
}
