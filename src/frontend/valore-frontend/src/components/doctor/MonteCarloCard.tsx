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
import { useMediaQuery } from '@mantine/hooks';
import { IconTrendingUp } from '@tabler/icons-react';
import {
  Area,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
  ComposedChart,
} from 'recharts';
import { useMonteCarloProjection } from '../dashboard/hooks/queries';
import { STORAGE_KEYS } from '../dashboard/constants';
import type { MonteCarloYearProjection } from '../../services/api';

const PRIVACY_MASK = '******';

function isPrivacyModeEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled) === 'true';
}

interface Props {
  portfolioId: number | null;
  marketValue: number | null;
  currency: string;
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

function formatCurrency(value: number, currency: string): string {
  if (isPrivacyModeEnabled()) return PRIVACY_MASK;
  return value.toLocaleString('it-IT', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

function indexToValue(index: number, marketValue: number): number {
  return (index / 100) * marketValue;
}

export function MonteCarloCard({ portfolioId, marketValue, currency }: Props) {
  const { data, isLoading, error } = useMonteCarloProjection(portfolioId);
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  const isMobile = useMediaQuery('(max-width: 48em)');
  const hasValue = marketValue != null && marketValue > 0;

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
          <div style={{ minWidth: 0 }}>
            <Title order={4}>Proiezione Monte Carlo</Title>
            <Text size="xs" c="dimmed" style={{ wordBreak: 'break-word' }}>
              {data.num_simulations.toLocaleString()} sim. &middot; rend. medio {data.annualized_mean_return_pct.toFixed(1)}% &middot; vol. {data.annualized_volatility_pct.toFixed(1)}%
              {hasValue && <> &middot; valore {formatCurrency(marketValue, currency)}</>}
            </Text>
          </div>
        </Group>

        <Box style={{ width: '100%', height: 320, overflow: 'hidden' }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 10, right: isMobile ? 5 : 10, left: isMobile ? -15 : 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={isDark ? theme.colors.dark[4] : '#e2e8f0'} />
              <XAxis
                dataKey="year"
                tick={{ fontSize: isMobile ? 10 : 12 }}
                tickFormatter={(v) => v === '0' ? 'Oggi' : `${v}a`}
              />
              <YAxis
                yAxisId="left"
                tick={{ fontSize: isMobile ? 10 : 12 }}
                tickFormatter={(v: number) => `${v}`}
                domain={['auto', 'auto']}
                width={isMobile ? 35 : 60}
              />
              {hasValue && !isMobile && (
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: number) => formatCurrency(indexToValue(v, marketValue), currency)}
                  domain={['auto', 'auto']}
                />
              )}
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
                      {[
                        { label: 'P90', val: d.p90 },
                        { label: 'P75', val: d.p75 },
                        { label: 'P50', val: d.p50, bold: true },
                        { label: 'P25', val: d.p25 },
                        { label: 'P10', val: d.p10 },
                      ].map(({ label, val, bold }) => (
                        <Text key={label} size="xs" c={bold ? undefined : 'dimmed'} fw={bold ? 600 : undefined}>
                          {label}: {formatGrowth(val)}
                          {hasValue && ` (${formatCurrency(indexToValue(val, marketValue), currency)})`}
                        </Text>
                      ))}
                    </Box>
                  );
                }}
              />
              <ReferenceLine yAxisId="left" y={100} stroke={isDark ? theme.colors.dark[3] : '#94a3b8'} strokeDasharray="4 4" />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="p90"
                stroke="none"
                fill={lightTeal}
                fillOpacity={0.5}
                isAnimationActive={false}
              />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="p75"
                stroke="none"
                fill={midTeal}
                fillOpacity={0.5}
                isAnimationActive={false}
              />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="p25"
                stroke="none"
                fill={isDark ? theme.colors.dark[7] : 'white'}
                fillOpacity={1}
                isAnimationActive={false}
              />
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="p10"
                stroke="none"
                fill={isDark ? theme.colors.dark[7] : 'white'}
                fillOpacity={1}
                isAnimationActive={false}
              />
              <Line
                yAxisId="left"
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
            <HorizonSummary
              key={horizon}
              years={horizon}
              projection={projection}
              isDark={isDark}
              marketValue={hasValue ? marketValue : null}
              currency={currency}
            />
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
  marketValue,
  currency,
}: {
  years: number;
  projection: MonteCarloYearProjection | undefined;
  isDark: boolean;
  marketValue: number | null;
  currency: string;
}) {
  const theme = useMantineTheme();

  if (!projection) return null;

  const hasValue = marketValue != null && marketValue > 0;

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
      <Text fw={800} size="lg" style={{ wordBreak: 'break-word' }}>
        {formatGrowth(projection.p50)}
      </Text>
      {hasValue && (
        <Text size="sm" fw={600} c="dimmed" style={{ wordBreak: 'break-word' }}>
          {formatCurrency(indexToValue(projection.p50, marketValue), currency)}
        </Text>
      )}
      <Text size="xs" c="dimmed" style={{ wordBreak: 'break-word' }}>
        Range: {formatGrowth(projection.p10)} / {formatGrowth(projection.p90)}
      </Text>
      {hasValue && (
        <Text size="xs" c="dimmed" style={{ wordBreak: 'break-word' }}>
          {formatCurrency(indexToValue(projection.p10, marketValue), currency)} / {formatCurrency(indexToValue(projection.p90, marketValue), currency)}
        </Text>
      )}
    </Box>
  );
}
