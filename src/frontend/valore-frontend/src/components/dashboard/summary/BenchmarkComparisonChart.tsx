import { Badge, Card, Group, Loader, Paper, SegmentedControl, Select, Text } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { DASHBOARD_WINDOWS } from '../constants';
import { formatPct, getVariationColor } from '../formatters';

interface ComparisonPoint {
  rawDate: string;
  date: string;
  portfolio: number;
  benchmark: number;
}

interface BenchmarkComparisonChartProps {
  data: ComparisonPoint[];
  loading: boolean;
  chartWindow: string;
  onChartWindowChange: (w: string) => void;
  chartWindowDays: number;
  benchmarkSelectData: Array<{ value: string; label: string }>;
  selectedBenchmarkId: number | null;
  onBenchmarkChange: (id: number | null) => void;
  comparisonStats?: { pPct: number; bPct: number; benchLabel: string };
}

export function BenchmarkComparisonChart({
  data,
  loading,
  chartWindow,
  onChartWindowChange,
  chartWindowDays,
  benchmarkSelectData,
  selectedBenchmarkId,
  onBenchmarkChange,
  comparisonStats,
}: BenchmarkComparisonChartProps) {
  const isMobile = useMediaQuery('(max-width: 48em)');
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const gridColor = isDark ? theme.colors.dark[4] : '#e9ecef';
  const tickColor = isDark ? theme.colors.dark[1] : '#868e96';

  return (
    <Card withBorder radius="md" p="md" shadow="sm">
      <Group justify="space-between" mb="xs" align={isMobile ? 'flex-start' : 'center'} wrap="wrap" gap="xs">
        <Group gap="xs">
          <Text fw={600} size="sm">
            {`Andamento Portafoglio vs ${comparisonStats?.benchLabel ?? 'Benchmark'} (${chartWindow === '1' ? '1g' : `${chartWindowDays}g`})`}
          </Text>
          {comparisonStats && (
            <>
              <Badge variant="light" color={getVariationColor(comparisonStats.pPct)} size={isMobile ? 'lg' : 'md'}
                styles={{ root: { fontSize: isMobile ? 14 : 13, fontWeight: 600, paddingInline: isMobile ? 12 : 10, height: isMobile ? 32 : 28 } }}>
                Portafoglio {formatPct(comparisonStats.pPct)}
              </Badge>
              <Badge variant="light" color={getVariationColor(comparisonStats.bPct)} size={isMobile ? 'lg' : 'md'}
                styles={{ root: { fontSize: isMobile ? 14 : 13, fontWeight: 600, paddingInline: isMobile ? 12 : 10, height: isMobile ? 32 : 28 } }}>
                {comparisonStats.benchLabel} {formatPct(comparisonStats.bPct)}
              </Badge>
            </>
          )}
        </Group>
        <Group gap="xs" style={isMobile ? { width: '100%' } : undefined}>
          <Select
            size={isMobile ? 'sm' : 'xs'}
            w={isMobile ? '100%' : 140}
            data={benchmarkSelectData}
            value={selectedBenchmarkId != null ? String(selectedBenchmarkId) : ''}
            onChange={(v) => onBenchmarkChange(v ? Number(v) : null)}
            allowDeselect={false}
          />
          <SegmentedControl
            size={isMobile ? 'sm' : 'xs'}
            value={chartWindow}
            onChange={onChartWindowChange}
            data={DASHBOARD_WINDOWS.map((w) => ({ label: w.label, value: w.value }))}
            fullWidth={isMobile}
          />
        </Group>
      </Group>
      <Text size="xs" c="dimmed" mb="sm">Entrambe le serie normalizzate a base 100</Text>
      <div style={{ height: isMobile ? 320 : 260 }}>
        {loading ? (
          <Group h="100%" justify="center">
            <Loader size="sm" />
            <Text c="dimmed" size="sm">Caricamento benchmark...</Text>
          </Group>
        ) : data.length === 0 ? (
          <Group h="100%" justify="center">
            <Text c="dimmed" size="sm">Nessun dato di prezzo disponibile per il benchmark. Prova ad aggiornare i prezzi.</Text>
          </Group>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id="compPortfolioGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#16a34a" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#16a34a" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridColor} />
              <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: tickColor, fontSize: 12 }} />
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip
                content={({ active, payload, label }: any) => {
                  if (!active || !payload?.length) return null;
                  const pv = Number(payload.find((p: any) => p.dataKey === 'portfolio')?.value ?? 0);
                  const bv = Number(payload.find((p: any) => p.dataKey === 'benchmark')?.value ?? 0);
                  return (
                    <Paper withBorder p="xs" radius="sm" shadow="xs">
                      <Text size="xs" c="dimmed">{`Data ${label}`}</Text>
                      <Text size="sm" fw={600} c="#16a34a">{`Portafoglio: ${formatPct(pv - 100)}`}</Text>
                      <Text size="sm" fw={600} c="#2563eb">{`${comparisonStats?.benchLabel ?? 'Benchmark'}: ${formatPct(bv - 100)}`}</Text>
                    </Paper>
                  );
                }}
              />
              <Legend
                verticalAlign="top"
                height={28}
                formatter={(value: string) => (value === 'portfolio' ? 'Portafoglio' : (comparisonStats?.benchLabel ?? 'Benchmark'))}
              />
              <Area
                type="monotone"
                dataKey="portfolio"
                stroke="#16a34a"
                strokeWidth={2.5}
                fillOpacity={1}
                fill="url(#compPortfolioGrad)"
              />
              <Area
                type="monotone"
                dataKey="benchmark"
                stroke="#2563eb"
                strokeWidth={2}
                strokeDasharray="5 5"
                fillOpacity={0}
                fill="transparent"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
