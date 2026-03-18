import { Badge, Box, Group, Progress, RingProgress, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconShieldCheck, IconChartDonut, IconStack2, IconCoin, IconTarget } from '@tabler/icons-react';
import type { InstantAnalyzeResponse } from '../../services/api';

interface InstantAnalyzerScoreCardProps {
  result: InstantAnalyzeResponse;
}

function summaryTone(score: number): { label: string; color: string; emeraldShade: string } {
  if (score >= 80) return { label: 'Eccellente', color: 'teal', emeraldShade: '#10b981' };
  if (score >= 70) return { label: 'Buono', color: 'teal', emeraldShade: '#10b981' };
  if (score >= 60) return { label: 'Medio', color: 'yellow', emeraldShade: '#eab308' };
  return { label: 'Debole', color: 'red', emeraldShade: '#ef4444' };
}

const SUMMARY_LABELS: Record<string, string> = {
  low: 'Basso', medium: 'Medio', high: 'Alto', unknown: 'N/D',
  excellent: 'Eccellente', good: 'Buona', moderate: 'Moderata', weak: 'Debole',
  low_cost: 'Bassi', moderate_cost: 'Moderati', high_cost: 'Alti',
};

const CATEGORY_CONFIG = [
  { key: 'diversification', label: 'Diversificazione', max: 25, icon: IconChartDonut, color: 'teal' },
  { key: 'risk', label: 'Rischio', max: 25, icon: IconShieldCheck, color: 'red' },
  { key: 'concentration', label: 'Concentrazione', max: 20, icon: IconTarget, color: 'orange' },
  { key: 'overlap', label: 'Overlap', max: 15, icon: IconStack2, color: 'grape' },
  { key: 'cost_efficiency', label: 'Costi', max: 15, icon: IconCoin, color: 'cyan' },
] as const;

export function InstantAnalyzerScoreCard({ result }: InstantAnalyzerScoreCardProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const tone = summaryTone(result.summary.score);

  const emerald = '#10b981';

  return (
    <Box
      style={{
        borderRadius: 16,
        border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
        background: isDark
          ? theme.colors.dark[6]
          : '#ffffff',
        padding: 24,
        boxShadow: isDark ? 'none' : '0 1px 3px rgba(0,0,0,0.04)',
      }}
    >
      <Stack gap="lg">
        {/* Score header */}
        <Group justify="space-between" align="center" wrap="nowrap">
          <Group gap="lg" align="center" wrap="nowrap">
            <RingProgress
              size={90}
              thickness={8}
              roundCaps
              sections={[{ value: result.summary.score, color: tone.emeraldShade }]}
              label={
                <Text ta="center" fw={800} size="xl" c={isDark ? 'white' : '#111827'}>
                  {result.summary.score}
                </Text>
              }
            />
            <Stack gap={2}>
              <Text tt="uppercase" fw={800} size="xs" c={emerald} style={{ letterSpacing: '0.05em' }}>
                Salute del Portafoglio
              </Text>
              <Title order={3} c={isDark ? 'white' : '#111827'}>
                {tone.label}
              </Title>
              <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
                Valore: EUR {result.summary.total_value.toLocaleString('it-IT')}
              </Text>
            </Stack>
          </Group>
          <Badge
            color={tone.color}
            size="xl"
            radius="md"
            variant="light"
            style={{ fontWeight: 800 }}
          >
            {result.summary.score}/100
          </Badge>
        </Group>

        {/* Summary badges */}
        <SimpleGrid cols={{ base: 2, md: 4 }} spacing="sm">
          {[
            { label: 'Rischio', value: result.summary.risk_level, color: result.summary.risk_level === 'low' ? 'teal' : result.summary.risk_level === 'high' ? 'red' : 'yellow' },
            { label: 'Diversificazione', value: result.summary.diversification, color: result.summary.diversification === 'excellent' ? 'teal' : result.summary.diversification === 'good' ? 'teal' : 'orange' },
            { label: 'Overlap', value: result.summary.overlap, color: result.summary.overlap === 'low' ? 'teal' : result.summary.overlap === 'high' ? 'red' : 'yellow' },
            { label: 'Costi', value: result.summary.cost_efficiency, color: result.summary.cost_efficiency === 'low_cost' ? 'teal' : result.summary.cost_efficiency === 'high_cost' ? 'red' : 'yellow' },
          ].map((item) => (
            <Stack
              key={item.label}
              gap={4}
              style={{
                padding: '10px 14px',
                borderRadius: 12,
                background: isDark ? theme.colors.dark[5] : '#f9fafb',
                border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
              }}
            >
              <Text size="xs" tt="uppercase" fw={700} c={isDark ? theme.colors.gray[5] : '#9ca3af'} style={{ letterSpacing: '0.03em' }}>
                {item.label}
              </Text>
              <Badge color={item.color} variant="light" size="md" radius="sm" style={{ alignSelf: 'flex-start' }}>
                {SUMMARY_LABELS[item.value] ?? item.value}
              </Badge>
            </Stack>
          ))}
        </SimpleGrid>

        {/* Category scores */}
        <SimpleGrid cols={{ base: 2, sm: 3, md: 5 }} spacing="sm">
          {CATEGORY_CONFIG.map(({ key, label, max, icon: Icon, color }) => {
            const score = result.category_scores[key as keyof typeof result.category_scores] ?? 0;
            const pct = max > 0 ? (score / max) * 100 : 0;
            return (
              <Stack
                key={key}
                gap={6}
                style={{
                  padding: 12,
                  borderRadius: 12,
                  background: isDark ? theme.colors.dark[5] : '#f9fafb',
                  border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
                }}
              >
                <Group gap={6} wrap="nowrap">
                  <ThemeIcon color={color} variant="light" size="sm" radius="xl">
                    <Icon size={12} />
                  </ThemeIcon>
                  <Text size="xs" fw={700} c={isDark ? theme.colors.gray[4] : '#6b7280'}>
                    {label}
                  </Text>
                </Group>
                <Progress value={pct} color={color} size="sm" radius="xl" />
                <Text fw={800} size="sm" c={isDark ? 'white' : '#111827'}>
                  {score} / {max}
                </Text>
              </Stack>
            );
          })}
        </SimpleGrid>
      </Stack>
    </Box>
  );
}
