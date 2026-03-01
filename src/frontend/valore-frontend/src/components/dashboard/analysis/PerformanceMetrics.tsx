import { useEffect, useMemo, useState } from 'react';
import { Alert, Card, Group, Loader, SegmentedControl, SimpleGrid, Text } from '@mantine/core';
import { getPerformanceSummary, type PerformanceSummary } from '../../../services/api';

type PeriodKey = '1m' | '3m' | '6m' | 'ytd' | '1y' | '3y' | 'all';

interface PerformanceMetricsProps {
  portfolioId: number | null;
}

const PERIOD_OPTIONS: Array<{ label: string; value: PeriodKey }> = [
  { label: '1M', value: '1m' },
  { label: '3M', value: '3m' },
  { label: '6M', value: '6m' },
  { label: 'YTD', value: 'ytd' },
  { label: '1Y', value: '1y' },
  { label: '3Y', value: '3y' },
  { label: 'ALL', value: 'all' },
];

function formatMoney(value: number, currency = 'EUR'): string {
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function kpiColor(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'var(--mantine-color-dimmed)';
  return value >= 0 ? 'var(--mantine-color-green-7)' : 'var(--mantine-color-red-7)';
}

export function PerformanceMetrics({ portfolioId }: PerformanceMetricsProps) {
  const [period, setPeriod] = useState<PeriodKey>('1y');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<PerformanceSummary | null>(null);

  useEffect(() => {
    if (!portfolioId) {
      setSummary(null);
      setError(null);
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);

    getPerformanceSummary(portfolioId, period)
      .then((res) => {
        if (!active) return;
        setSummary(res);
      })
      .catch((err) => {
        if (!active) return;
        setSummary(null);
        setError(err instanceof Error ? err.message : 'Errore caricamento metriche performance');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [portfolioId, period]);

  const currency = useMemo(() => {
    return 'EUR';
  }, []);

  return (
    <Card withBorder radius="md" p="md" shadow="sm" mb="md">
      <Group justify="space-between" mb="sm" wrap="wrap" gap="xs">
        <Text fw={600}>Performance</Text>
        <SegmentedControl
          size="xs"
          value={period}
          onChange={(value) => setPeriod((value as PeriodKey) ?? '1y')}
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
          <Text fw={700}>{summary ? formatMoney(summary.net_invested, currency) : 'N/D'}</Text>
        </Card>

        <Card withBorder radius="md" p="sm">
          <Text size="sm" c="dimmed">Versato</Text>
          <Text fw={700}>{summary ? formatMoney(summary.total_deposits, currency) : 'N/D'}</Text>
        </Card>

        <Card withBorder radius="md" p="sm">
          <Text size="sm" c="dimmed">Prelevato</Text>
          <Text fw={700}>{summary ? formatMoney(summary.total_withdrawals, currency) : 'N/D'}</Text>
        </Card>

        <Card withBorder radius="md" p="sm">
          <Text size="sm" c="dimmed">Guadagno Assoluto</Text>
          <Text fw={700} style={{ color: kpiColor(summary?.absolute_gain) }}>
            {summary ? formatMoney(summary.absolute_gain, currency) : 'N/D'}
          </Text>
        </Card>
      </SimpleGrid>
    </Card>
  );
}
