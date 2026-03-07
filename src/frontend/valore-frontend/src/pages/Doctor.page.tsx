import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Container,
  CopyButton,
  Grid,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
  useComputedColorScheme,
  useMantineTheme,
} from '@mantine/core';
import {
  IconAlertTriangle,
  IconCheck,
  IconCopy,
  IconHeartRateMonitor,
  IconLink,
  IconShare,
  IconSparkles,
} from '@tabler/icons-react';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { usePortfolioHealth, usePortfolios } from '../components/dashboard/hooks/queries';

function scoreTone(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Excellent', color: 'teal' };
  if (score >= 70) return { label: 'Good', color: 'blue' };
  if (score >= 60) return { label: 'Average', color: 'yellow' };
  return { label: 'Weak', color: 'red' };
}

function formatPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return `${value.toFixed(1)}%`;
}

function humanize(value: string): string {
  return value.replace(/_/g, ' ');
}

export function DoctorPage() {
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId);
  });

  const { data: portfolios = [], isLoading: portfoliosLoading, error: portfoliosError } = usePortfolios();
  const portfolioId = selectedPortfolioId ? Number(selectedPortfolioId) : null;
  const { data: health, isLoading: healthLoading, error: healthError } = usePortfolioHealth(portfolioId);

  useEffect(() => {
    if (!portfolios.length) return;
    setSelectedPortfolioId((previous) => {
      const exists = previous ? portfolios.some((portfolio) => String(portfolio.id) === previous) : false;
      return exists ? previous : String(portfolios[0].id);
    });
  }, [portfolios]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (selectedPortfolioId) {
      window.localStorage.setItem(STORAGE_KEYS.selectedPortfolioId, selectedPortfolioId);
    }
  }, [selectedPortfolioId]);

  const selectedPortfolio = useMemo(
    () => portfolios.find((portfolio) => String(portfolio.id) === selectedPortfolioId) ?? null,
    [portfolios, selectedPortfolioId],
  );

  const shareSummary = useMemo(() => {
    if (!health || !selectedPortfolio) return '';
    const alerts = health.alerts.slice(0, 2).map((alert) => `- ${alert.message}`).join('\n');
    const suggestions = health.suggestions.slice(0, 2).map((suggestion) => `- ${suggestion.message}`).join('\n');
    return [
      `${selectedPortfolio.name} Portfolio Doctor`,
      `Score: ${health.score}/100`,
      `Risk: ${humanize(health.summary.risk_level)}`,
      `Diversification: ${humanize(health.summary.diversification)}`,
      `Overlap: ${humanize(health.summary.overlap)}`,
      `Costs: ${humanize(health.summary.cost_efficiency)}`,
      alerts ? `Warnings:\n${alerts}` : '',
      suggestions ? `Suggestions:\n${suggestions}` : '',
    ].filter(Boolean).join('\n');
  }, [health, selectedPortfolio]);

  const tone = scoreTone(health?.score ?? 0);
  const colorScheme = useComputedColorScheme('light');
  const theme = useMantineTheme();
  const isDark = colorScheme === 'dark';
  const pageError = (portfoliosError instanceof Error ? portfoliosError.message : null)
    || (healthError instanceof Error ? healthError.message : null);

  return (
    <Box
      style={{
        minHeight: '100%',
        background: isDark
          ? `radial-gradient(circle at top left, rgba(19,78,74,0.18), transparent 24%), linear-gradient(180deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[7]} 26%, ${theme.colors.dark[9]} 100%)`
          : 'radial-gradient(circle at top left, rgba(19,78,74,0.10), transparent 24%), linear-gradient(180deg, #f7fbfa 0%, #ffffff 26%, #fffaf1 100%)',
        padding: 'var(--mantine-spacing-sm)',
      }}
    >
      <Container fluid>
        <Stack gap="lg">
          <Group justify="space-between" align="flex-end" wrap="wrap" gap="xs">
            <div>
              <Group gap="sm" mb={8}>
                <ThemeIcon radius="xl" color="teal" variant="light">
                  <IconHeartRateMonitor size={18} />
                </ThemeIcon>
                <Text fw={800} tt="uppercase" size="xs" c="dimmed">Share-ready diagnostics</Text>
              </Group>
              <Title order={2}>Doctor</Title>
              <Text c="dimmed" maw={680}>
                A portfolio checkup designed to be readable, screenshot-friendly, and ready to share.
              </Text>
            </div>

            <PortfolioSwitcher
              portfolios={portfolios}
              value={selectedPortfolioId}
              onChange={(nextValue) => setSelectedPortfolioId(nextValue)}
              loading={portfoliosLoading}
              style={{ width: '100%', maxWidth: 360 }}
            />
          </Group>

          {pageError && <Alert color="red">{pageError}</Alert>}

          {!selectedPortfolio && !portfoliosLoading && (
            <Alert color="yellow">
              Create a portfolio first, then come back here for a Doctor report.
            </Alert>
          )}

          {healthLoading && portfolioId != null && (
            <Card withBorder radius="xl" padding="xl">
              <Group justify="center" py="xl">
                <Loader />
              </Group>
            </Card>
          )}

          {health && selectedPortfolio && (
            <>
              <Grid gutter="lg" align="stretch">
                <Grid.Col span={{ base: 12, xl: 8 }}>
                  <Card
                    radius="xl"
                    padding="xl"
                    withBorder
                    style={{ background: 'linear-gradient(140deg, #103c39 0%, #1f5d59 58%, #f0b24f 160%)', color: 'white' }}
                  >
                    <Stack gap="lg">
                      <Group justify="space-between" align="flex-start" wrap="wrap">
                        <div>
                          <Text tt="uppercase" fw={800} size="xs" style={{ opacity: 0.72 }}>Portfolio Doctor</Text>
                          <Title order={1} mt={6} c="white" style={{ fontSize: 'clamp(3rem, 7vw, 5.5rem)', lineHeight: 0.95 }}>
                            {health.score}
                            <Text component="span" inherit style={{ opacity: 0.72 }}> / 100</Text>
                          </Title>
                          <Text c="rgba(255,255,255,0.82)" mt="sm" size="lg">
                            {selectedPortfolio.name}
                          </Text>
                        </div>
                        <Badge size="xl" radius="sm" color={tone.color} variant="filled">
                          {tone.label}
                        </Badge>
                      </Group>

                      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
                        <MetricChip label="Risk" value={health.summary.risk_level} />
                        <MetricChip label="Diversification" value={health.summary.diversification} />
                        <MetricChip label="Overlap" value={health.summary.overlap} />
                        <MetricChip label="Costs" value={health.summary.cost_efficiency} />
                      </SimpleGrid>

                      <Group gap="sm" wrap="wrap">
                        <CopyButton value={shareSummary}>
                          {({ copied, copy }) => (
                            <Button
                              variant="white"
                              color="dark"
                              leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                              onClick={copy}
                              radius="xl"
                            >
                              {copied ? 'Summary copied' : 'Copy summary'}
                            </Button>
                          )}
                        </CopyButton>
                        <CopyButton value={typeof window !== 'undefined' ? window.location.href : '/doctor'}>
                          {({ copied, copy }) => (
                            <Button
                              variant="outline"
                              color="gray"
                              leftSection={copied ? <IconCheck size={16} /> : <IconLink size={16} />}
                              onClick={copy}
                              radius="xl"
                            >
                              {copied ? 'Link copied' : 'Copy link'}
                            </Button>
                          )}
                        </CopyButton>
                        <Badge variant="light" color="yellow" leftSection={<IconShare size={12} />}>
                          Built for screenshot sharing
                        </Badge>
                      </Group>
                    </Stack>
                  </Card>
                </Grid.Col>

                <Grid.Col span={{ base: 12, xl: 4 }}>
                  <Card withBorder radius="xl" padding="lg" h="100%">
                    <Stack gap="md">
                      <Group gap="sm">
                        <ThemeIcon color="yellow" variant="light" radius="xl">
                          <IconSparkles size={18} />
                        </ThemeIcon>
                        <Title order={4}>Top signals</Title>
                      </Group>
                      {health.alerts.slice(0, 2).map((alert) => (
                        <Alert key={`${alert.type}-${alert.message}`} color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light">
                          {alert.message}
                        </Alert>
                      ))}
                      {!health.alerts.length && (
                        <Alert color="teal" variant="light">
                          No major structural warnings were detected.
                        </Alert>
                      )}
                      {health.suggestions.slice(0, 2).map((suggestion) => (
                        <Alert key={suggestion.message} color="teal" variant="light">
                          {suggestion.message}
                        </Alert>
                      ))}
                    </Stack>
                  </Card>
                </Grid.Col>
              </Grid>

              <Grid gutter="lg" align="start">
                <Grid.Col span={{ base: 12, lg: 6 }}>
                  <Card withBorder radius="xl" padding="lg">
                    <Title order={4} mb="md">Metric breakdown</Title>
                    <Table withTableBorder withColumnBorders highlightOnHover>
                      <Table.Tbody>
                        <Table.Tr><Table.Td>USA exposure</Table.Td><Table.Td>{formatPct(health.metrics.geographic_exposure.usa)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td>Europe exposure</Table.Td><Table.Td>{formatPct(health.metrics.geographic_exposure.europe)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td>Emerging exposure</Table.Td><Table.Td>{formatPct(health.metrics.geographic_exposure.emerging)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td>Max position weight</Table.Td><Table.Td>{formatPct(health.metrics.max_position_weight)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td>Overlap score</Table.Td><Table.Td>{formatPct(health.metrics.overlap_score)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td>Volatility</Table.Td><Table.Td>{formatPct(health.metrics.portfolio_volatility)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td>Weighted TER</Table.Td><Table.Td>{formatPct(health.metrics.weighted_ter)}</Table.Td></Table.Tr>
                      </Table.Tbody>
                    </Table>
                  </Card>
                </Grid.Col>

                <Grid.Col span={{ base: 12, lg: 6 }}>
                  <Card withBorder radius="xl" padding="lg">
                    <Title order={4} mb="md">Category scores</Title>
                    <SimpleGrid cols={2} spacing="md">
                      <ScorePill label="Diversification" value={`${health.category_scores.diversification} / 25`} isDark={isDark} />
                      <ScorePill label="Risk" value={`${health.category_scores.risk} / 25`} isDark={isDark} />
                      <ScorePill label="Concentration" value={`${health.category_scores.concentration} / 20`} isDark={isDark} />
                      <ScorePill label="Overlap" value={`${health.category_scores.overlap} / 15`} isDark={isDark} />
                      <ScorePill label="Cost efficiency" value={`${health.category_scores.cost_efficiency} / 15`} isDark={isDark} />
                    </SimpleGrid>
                  </Card>
                </Grid.Col>
              </Grid>

              <Grid gutter="lg" align="start">
                <Grid.Col span={{ base: 12, lg: 6 }}>
                  <Card withBorder radius="xl" padding="lg">
                    <Group gap="sm" mb="md">
                      <ThemeIcon color="orange" variant="light" radius="xl">
                        <IconAlertTriangle size={18} />
                      </ThemeIcon>
                      <Title order={4}>All warnings</Title>
                    </Group>
                    <Stack gap="sm">
                      {health.alerts.length ? health.alerts.map((alert) => (
                        <Alert key={`${alert.type}-${alert.message}`} color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light">
                          {alert.message}
                        </Alert>
                      )) : <Text c="dimmed">No warnings.</Text>}
                    </Stack>
                  </Card>
                </Grid.Col>

                <Grid.Col span={{ base: 12, lg: 6 }}>
                  <Card withBorder radius="xl" padding="lg">
                    <Group gap="sm" mb="md">
                      <ThemeIcon color="teal" variant="light" radius="xl">
                        <IconSparkles size={18} />
                      </ThemeIcon>
                      <Title order={4}>Improvement ideas</Title>
                    </Group>
                    <Stack gap="sm">
                      {health.suggestions.length ? health.suggestions.map((suggestion) => (
                        <Alert key={suggestion.message} color="teal" variant="light">
                          {suggestion.message}
                        </Alert>
                      )) : <Text c="dimmed">No suggestions.</Text>}
                    </Stack>
                  </Card>
                </Grid.Col>
              </Grid>
            </>
          )}
        </Stack>
      </Container>
    </Box>
  );
}

function MetricChip({ label, value }: { label: string; value: string }) {
  return (
    <Box
      style={{
        borderRadius: 16,
        padding: '14px 16px',
        background: 'rgba(255,255,255,0.12)',
        border: '1px solid rgba(255,255,255,0.16)',
      }}
    >
      <Text size="xs" tt="uppercase" style={{ opacity: 0.7 }}>{label}</Text>
      <Text fw={700}>{humanize(value)}</Text>
    </Box>
  );
}

function ScorePill({ label, value, isDark }: { label: string; value: string; isDark: boolean }) {
  return (
    <Box
      style={{
        borderRadius: 18,
        padding: '14px 16px',
        background: isDark
          ? 'linear-gradient(180deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.03) 100%)'
          : 'linear-gradient(180deg, #f8fafc 0%, #ffffff 100%)',
        border: isDark ? '1px solid rgba(255,255,255,0.10)' : '1px solid #e2e8f0',
      }}
    >
      <Text size="sm" c="dimmed">{label}</Text>
      <Text fw={800} size="lg">{value}</Text>
    </Box>
  );
}
