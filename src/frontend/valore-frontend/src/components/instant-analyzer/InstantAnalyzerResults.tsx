import { Badge, Box, Button, Group, Progress, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { Paper } from '@mantine/core';
import { PieChart, Pie, Cell, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import {
  IconArrowRight,
  IconChartDonut3,
  IconGlobe,
  IconMapPin,
  IconStack2,
  IconChartLine,
  IconCoin,
  IconTarget,
} from '@tabler/icons-react';
import type { InstantAnalyzeResponse } from '../../services/api';
import { InstantAnalyzerInputIssues } from './InstantAnalyzerInputIssues';
import { InstantAnalyzerInsights } from './InstantAnalyzerInsights';
import { InstantAnalyzerScoreCard } from './InstantAnalyzerScoreCard';

interface InstantAnalyzerResultsProps {
  result: InstantAnalyzeResponse;
}

const clerkEnabled = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

const COLORS = ['#10b981', '#059669', '#0d9488', '#0891b2', '#6366f1', '#8b5cf6', '#ec4899', '#f59e0b'];

function formatPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return `${value.toFixed(1)}%`;
}

function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return value.toFixed(2);
}

const METRIC_CONFIG = [
  { key: 'usa', label: 'USA', icon: IconGlobe, color: 'blue' },
  { key: 'europe', label: 'Europa', icon: IconMapPin, color: 'indigo' },
  { key: 'emerging', label: 'Emergenti', icon: IconGlobe, color: 'teal' },
] as const;

export function InstantAnalyzerResults({ result }: InstantAnalyzerResultsProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  const textPrimary = isDark ? 'white' : '#111827';
  const textSecondary = isDark ? theme.colors.gray[4] : '#6b7280';
  const cardStyle = {
    borderRadius: 16,
    border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
    background: isDark ? theme.colors.dark[6] : '#ffffff',
    padding: 24,
    boxShadow: isDark ? 'none' : '0 1px 3px rgba(0,0,0,0.04)',
  };

  const pieData = result.positions.map((p) => ({
    name: p.resolved_symbol,
    value: Math.round(p.weight * 100) / 100,
  }));

  return (
    <Stack gap="lg">
      <InstantAnalyzerScoreCard result={result} />

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        {/* Geographic + key metrics */}
        <Box style={cardStyle}>
          <Group gap="sm" mb="md">
            <ThemeIcon color="teal" variant="light" radius="xl">
              <IconChartDonut3 size={18} />
            </ThemeIcon>
            <Title order={4} c={textPrimary}>Metriche chiave</Title>
          </Group>
          <Stack gap="md">
            <Text size="xs" tt="uppercase" fw={700} c={textSecondary} style={{ letterSpacing: '0.05em' }}>
              Esposizione geografica
            </Text>
            {METRIC_CONFIG.map(({ key, label, icon: Icon, color }) => {
              const val = result.metrics.geographic_exposure[key] ?? 0;
              return (
                <Group key={key} justify="space-between" align="center" wrap="nowrap">
                  <Group gap="xs" wrap="nowrap" style={{ flex: 1, minWidth: 0 }}>
                    <ThemeIcon color={color} variant="light" size="sm" radius="xl">
                      <Icon size={12} />
                    </ThemeIcon>
                    <Text size="sm" fw={600} c={textPrimary}>{label}</Text>
                  </Group>
                  <Group gap="sm" wrap="nowrap" style={{ flex: 2 }}>
                    <Progress value={val} color={color} size="sm" radius="xl" style={{ flex: 1 }} />
                    <Text size="sm" fw={700} c={textPrimary} style={{ minWidth: 48, textAlign: 'right' }}>
                      {formatPct(val)}
                    </Text>
                  </Group>
                </Group>
              );
            })}

            <div style={{ borderTop: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb', paddingTop: 12, marginTop: 4 }} />

            {[
              { label: 'Posizione max', value: formatPct(result.metrics.max_position_weight), icon: IconTarget, color: 'orange' },
              { label: 'Score overlap', value: formatPct(result.metrics.overlap_score), icon: IconStack2, color: 'grape' },
              { label: 'Volatilita', value: formatPct(result.metrics.portfolio_volatility), icon: IconChartLine, color: 'red' },
              { label: 'TER medio', value: formatPct(result.metrics.weighted_ter), icon: IconCoin, color: 'teal' },
              { label: 'Quota equity', value: formatPct(result.metrics.asset_allocation?.Equity), icon: IconChartDonut3, color: 'blue' },
              { label: 'Drawdown stimato', value: formatPct(result.metrics.estimated_drawdown), icon: IconChartLine, color: 'orange' },
              { label: 'Risk score', value: formatNumber(result.metrics.risk_score), icon: IconTarget, color: 'gray' },
            ].map(({ label, value, icon: Icon, color }) => (
              <Group key={label} justify="space-between" wrap="nowrap">
                <Group gap="xs" wrap="nowrap">
                  <ThemeIcon color={color} variant="light" size="sm" radius="xl">
                    <Icon size={12} />
                  </ThemeIcon>
                  <Text size="sm" fw={600} c={textPrimary}>{label}</Text>
                </Group>
                <Text size="sm" fw={700} c={textPrimary}>{value}</Text>
              </Group>
            ))}
          </Stack>
        </Box>

        {/* Allocation doughnut + positions */}
        <Box style={cardStyle}>
          <Title order={4} mb="md" c={textPrimary}>Allocazione</Title>
          {pieData.length > 0 && (
            <div style={{ height: 200, position: 'relative', marginBottom: 12 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={75}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                  >
                    {pieData.map((_, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    content={({ active, payload }: any) => {
                      if (!active || !payload?.length) return null;
                      const entry = payload[0];
                      return (
                        <Paper withBorder p="xs" radius="sm" shadow="xs">
                          <Text size="xs" fw={600}>{entry.name}</Text>
                          <Text size="xs" c="dimmed">{Number(entry.value).toFixed(1)}%</Text>
                        </Paper>
                      );
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center', pointerEvents: 'none' }}>
                <Text fw={800} size="lg" c={textPrimary}>{result.positions.length}</Text>
                <Text size="xs" c={textSecondary}>titoli</Text>
              </div>
            </div>
          )}
          <Stack gap="sm">
            {result.positions.map((position, index) => (
              <Group key={`${position.identifier}-${position.resolved_symbol}`} justify="space-between" align="center" wrap="nowrap">
                <Group gap="xs" wrap="nowrap" style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: COLORS[index % COLORS.length], flexShrink: 0 }} />
                  <Stack gap={0} style={{ minWidth: 0 }}>
                    <Text fw={700} size="sm" c={textPrimary} truncate>{position.resolved_symbol}</Text>
                    <Text size="xs" c={textSecondary} lineClamp={1}>{position.resolved_name}</Text>
                  </Stack>
                </Group>
                <Stack gap={0} align="flex-end" style={{ flexShrink: 0 }}>
                  <Badge variant="light" color="teal" size="sm">{position.weight.toFixed(1)}%</Badge>
                  <Text size="xs" c={textSecondary}>EUR {position.value.toLocaleString('it-IT')}</Text>
                </Stack>
              </Group>
            ))}
          </Stack>
        </Box>
      </SimpleGrid>

      <InstantAnalyzerInsights result={result} />

      <InstantAnalyzerInputIssues
        parseErrors={result.parse_errors}
        unresolved={result.unresolved}
      />

      {result.cta.show_signup && (
        <Box
          style={{
            borderRadius: 16,
            padding: 28,
            background: isDark
              ? `linear-gradient(135deg, ${theme.colors.dark[8]} 0%, rgba(16, 185, 129, 0.15) 100%)`
              : 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            color: 'white',
          }}
        >
          <Group justify="space-between" align="center" wrap="wrap" gap="md">
            <div>
              <Text tt="uppercase" fw={800} size="xs" style={{ opacity: 0.7, letterSpacing: '0.05em' }}>
                Prossimo passo
              </Text>
              <Title order={3} c="white" mt={4}>{result.cta.message}</Title>
            </div>
            <Button
              component="a"
              href={clerkEnabled ? '/sign-up' : '/portfolio'}
              rightSection={<IconArrowRight size={16} />}
              color="dark"
              variant="white"
              radius="md"
              size="md"
              style={{ fontWeight: 700 }}
            >
              Crea account gratis
            </Button>
          </Group>
        </Box>
      )}
    </Stack>
  );
}
