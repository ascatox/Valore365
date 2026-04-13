import { Alert, Card, Group, Loader, SegmentedControl, SimpleGrid, Stack, Text, Tooltip } from '@mantine/core';
import { formatMoney, formatPct } from '../formatters';
import { kpiColor, PERIOD_OPTIONS } from './utils';
import type { PeriodKey } from './utils';

function NdTooltip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Tooltip label={label} multiline w={280} withArrow>
      <Text fw={700} style={{ cursor: 'help' }}>{children}</Text>
    </Tooltip>
  );
}

interface PerformanceKpiSummaryProps {
  summary: any;
  loading: boolean;
  error: string | null;
  currency: string;
  period: PeriodKey;
  onPeriodChange: (period: PeriodKey) => void;
}

export function PerformanceKpiSummary({ summary, loading, error, currency, period, onPeriodChange }: PerformanceKpiSummaryProps) {
  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Group justify="space-between" mb="sm" wrap="wrap" gap="xs">
        <Text fw={600}>Performance</Text>
        <SegmentedControl
          size="xs"
          value={period}
          onChange={(value) => onPeriodChange((value as PeriodKey) ?? '1y')}
          data={PERIOD_OPTIONS}
        />
      </Group>

      {error && <Alert color="red" mb="sm">{error}</Alert>}

      {loading && (
        <Group mb="sm" gap="xs">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">Calcolo metriche in corso...</Text>
        </Group>
      )}

      <SimpleGrid cols={{ base: 2, md: 3 }} spacing="sm">
        <Card withBorder radius="md" p="sm">
          <Text size="sm" c="dimmed">Netto Investito</Text>
          <Text fw={700}>{summary ? formatMoney(summary.net_invested, currency) : (
            <NdTooltip label="Dati insufficienti per calcolare il netto investito">N/D</NdTooltip>
          )}</Text>
        </Card>

        <Card withBorder radius="md" p="sm">
          <Text size="sm" c="dimmed">Versato</Text>
          <Text fw={700}>{summary ? formatMoney(summary.total_deposits, currency) : (
            <NdTooltip label="Nessun deposito registrato nel periodo selezionato">N/D</NdTooltip>
          )}</Text>
        </Card>

        <Card withBorder radius="md" p="sm">
          <Text size="sm" c="dimmed">Prelevato</Text>
          <Text fw={700}>{summary ? formatMoney(summary.total_withdrawals, currency) : (
            <NdTooltip label="Nessun prelievo registrato nel periodo selezionato">N/D</NdTooltip>
          )}</Text>
        </Card>

        <Card withBorder radius="md" p="sm">
          <Text size="sm" c="dimmed">Guadagno Assoluto</Text>
          {summary ? (
            <Text fw={700} style={{ color: kpiColor(summary.absolute_gain) }}>
              {formatMoney(summary.absolute_gain, currency)}
            </Text>
          ) : (
            <NdTooltip label="Dati insufficienti per calcolare il guadagno assoluto">N/D</NdTooltip>
          )}
        </Card>

        <Card withBorder radius="md" p="sm">
          <Tooltip label="Time-Weighted Return — rendimento del portafoglio al netto dei flussi di cassa" multiline w={280} withArrow>
            <Text size="sm" c="dimmed" style={{ cursor: 'help' }}>TWR</Text>
          </Tooltip>
          {summary?.twr?.twr_pct != null ? (
            <Text fw={700} style={{ color: kpiColor(summary.twr.twr_pct) }}>
              {formatPct(summary.twr.twr_pct)}
            </Text>
          ) : (
            <NdTooltip label="Dati insufficienti o assenza di prezzi giornalieri per il calcolo del Time-Weighted Return">N/D</NdTooltip>
          )}
        </Card>

        <Card withBorder radius="md" p="sm">
          <Tooltip label="Money-Weighted Return — rendimento ponderato per i flussi di cassa dell'investitore" multiline w={280} withArrow>
            <Text size="sm" c="dimmed" style={{ cursor: 'help' }}>MWR</Text>
          </Tooltip>
          {summary?.mwr?.mwr_pct != null ? (
            <Text fw={700} style={{ color: kpiColor(summary.mwr.mwr_pct) }}>
              {formatPct(summary.mwr.mwr_pct)}
            </Text>
          ) : (
            <NdTooltip label="Dati insufficienti o assenza di flussi di cassa per il calcolo del Money-Weighted Return">N/D</NdTooltip>
          )}
        </Card>
      </SimpleGrid>
    </Card>
  );
}
