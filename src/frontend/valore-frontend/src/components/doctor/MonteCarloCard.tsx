import {
  Alert,
  Box,
  Card,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import { IconTrendingUp } from '@tabler/icons-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
  ComposedChart,
} from 'recharts';
import { useMonteCarloProjection } from '../dashboard/hooks/queries';
import type { MonteCarloYearProjection } from '../../services/api';

interface Props {
  portfolioId: number | null;
}

interface ChartDatum {
  year: string;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
}

function formatGrowth(value: number): string {
  const pct = value - 100;
  if (pct >= 0) return `+${pct.toFixed(0)}%`;
  return `${pct.toFixed(0)}%`;
}

export function MonteCarloCard({ portfolioId }: Props) {
  const { data, isLoading, error } = useMonteCarloProjection(portfolioId);
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  if (isLoading && portfolioId != null) {
    return (
      <Card withBorder radius="xl" padding="xl">
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      </Card>
    );
  }

  if (error) {
    return (
      <Card withBorder radius="xl" padding="lg">
        <Alert color="red">Errore nel caricamento della proiezione Monte Carlo.</Alert>
      </Card>
    );
  }

  if (!data || data.projections.length === 0) {
    return (
      <Card withBorder radius="xl" padding="lg">
        <Group gap="sm" mb="md">
          <ThemeIcon color="indigo" variant="light" radius="xl">
            <IconTrendingUp size={18} />
          </ThemeIcon>
          <Title order={4}>Proiezione Monte Carlo</Title>
        </Group>
        <Alert color="yellow" variant="light">
          Dati storici insufficienti per la simulazione Monte Carlo.
        </Alert>
      </Card>
    );
  }

  const chartData: ChartDatum[] = data.projections.map((p) => ({
    year: `${p.year}`,
    p10: p.p10,
    p25: p.p25,
    p50: p.p50,
    p75: p.p75,
    p90: p.p90,
  }));

  const horizonSnapshots = data.horizons.map((h) => {
    const p = data.projections.find((proj) => proj.year === h);
    return { horizon: h, projection: p };
  });

  const tealColor = theme.colors.teal[isDark ? 4 : 6];
  const lightTeal = theme.colors.teal[isDark ? 9 : 1];
  const midTeal = theme.colors.teal[isDark ? 8 : 2];

  return (
    <Card withBorder radius="xl" padding="lg">
      <Stack gap="md">
        <Group gap="sm">
          <ThemeIcon color="indigo" variant="light" radius="xl">
            <IconTrendingUp size={18} />
          </ThemeIcon>
          <div>
            <Title order={4}>Proiezione Monte Carlo</Title>
            <Text size="xs" c="dimmed">
              {data.num_simulations.toLocaleString()} simulazioni &middot; rendimento medio {data.annualized_mean_return_pct.toFixed(1)}% &middot; volatilità {data.annualized_volatility_pct.toFixed(1)}%
            </Text>
          </div>
        </Group>

        <Box style={{ width: '100%', height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? theme.colors.dark[4] : '#e2e8f0'} />
              <XAxis
                dataKey="year"
                tick={{ fontSize: 12 }}
                tickFormatter={(v) => v === '0' ? 'Oggi' : `${v}a`}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                tickFormatter={(v: number) => `${v}`}
                domain={['auto', 'auto']}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0]?.payload as ChartDatum;
                  return (
                    <Box
                      style={{
                        background: isDark ? theme.colors.dark[7] : 'white',
                        border: `1px solid ${isDark ? theme.colors.dark[4] : '#e2e8f0'}`,
                        borderRadius: 8,
                        padding: '8px 12px',
                      }}
                    >
                      <Text fw={700} size="sm" mb={4}>
                        {d.year === '0' ? 'Oggi' : `Anno ${d.year}`}
                      </Text>
                      <Text size="xs" c="dimmed">P90: {formatGrowth(d.p90)}</Text>
                      <Text size="xs" c="dimmed">P75: {formatGrowth(d.p75)}</Text>
                      <Text size="xs" fw={600}>P50: {formatGrowth(d.p50)}</Text>
                      <Text size="xs" c="dimmed">P25: {formatGrowth(d.p25)}</Text>
                      <Text size="xs" c="dimmed">P10: {formatGrowth(d.p10)}</Text>
                    </Box>
                  );
                }}
              />
              <ReferenceLine y={100} stroke={isDark ? theme.colors.dark[3] : '#94a3b8'} strokeDasharray="4 4" />
              <Area
                type="monotone"
                dataKey="p90"
                stroke="none"
                fill={lightTeal}
                fillOpacity={0.5}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="p75"
                stroke="none"
                fill={midTeal}
                fillOpacity={0.5}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="p25"
                stroke="none"
                fill={isDark ? theme.colors.dark[7] : 'white'}
                fillOpacity={1}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="p10"
                stroke="none"
                fill={isDark ? theme.colors.dark[7] : 'white'}
                fillOpacity={1}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="p50"
                stroke={tealColor}
                strokeWidth={2.5}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </Box>

        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
          {horizonSnapshots.map(({ horizon, projection }) => (
            <HorizonSummary key={horizon} years={horizon} projection={projection} isDark={isDark} />
          ))}
        </SimpleGrid>

        <Text size="xs" c="dimmed" fs="italic">
          Le proiezioni si basano sulla volatilità storica e non costituiscono previsioni di rendimento futuro.
        </Text>
      </Stack>
    </Card>
  );
}

function HorizonSummary({
  years,
  projection,
  isDark,
}: {
  years: number;
  projection: MonteCarloYearProjection | undefined;
  isDark: boolean;
}) {
  const theme = useMantineTheme();

  if (!projection) return null;

  return (
    <Box
      style={{
        borderRadius: 18,
        padding: '14px 16px',
        background: isDark
          ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
          : 'linear-gradient(180deg, #f8fafc 0%, #ffffff 100%)',
        border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e2e8f0',
      }}
    >
      <Text size="xs" tt="uppercase" c="dimmed" fw={700}>{years} anni</Text>
      <Text fw={800} size="lg">{formatGrowth(projection.p50)}</Text>
      <Text size="xs" c="dimmed">
        Range: {formatGrowth(projection.p10)} / {formatGrowth(projection.p90)}
      </Text>
    </Box>
  );
}
