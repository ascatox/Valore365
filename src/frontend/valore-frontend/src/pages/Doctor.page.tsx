import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
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
import { useMediaQuery } from '@mantine/hooks';
import {
  IconAlertTriangle,
  IconCheck,
  IconCopy,
  IconLink,
  IconShare,
  IconSparkles,
} from '@tabler/icons-react';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { usePortfolioHealth, usePortfolios } from '../components/dashboard/hooks/queries';

function scoreTone(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Eccellente', color: 'teal' };
  if (score >= 70) return { label: 'Buono', color: 'blue' };
  if (score >= 60) return { label: 'Nella media', color: 'yellow' };
  return { label: 'Debole', color: 'red' };
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
      `${selectedPortfolio.name} — Diagnosi Portafoglio`,
      `Punteggio: ${health.score}/100`,
      `Rischio: ${humanize(health.summary.risk_level)}`,
      `Diversificazione: ${humanize(health.summary.diversification)}`,
      `Sovrapposizione: ${humanize(health.summary.overlap)}`,
      `Costi: ${humanize(health.summary.cost_efficiency)}`,
      alerts ? `Avvisi:\n${alerts}` : '',
      suggestions ? `Suggerimenti:\n${suggestions}` : '',
    ].filter(Boolean).join('\n');
  }, [health, selectedPortfolio]);

  const tone = scoreTone(health?.score ?? 0);
  const colorScheme = useComputedColorScheme('light');
  const theme = useMantineTheme();
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');
  const pageError = (portfoliosError instanceof Error ? portfoliosError.message : null)
    || (healthError instanceof Error ? healthError.message : null);

  const cardBg = isDark ? theme.colors.dark[7] : undefined;
  const cardBorder = isDark ? `1px solid ${theme.colors.dark[5]}` : undefined;

  return (
    <Box
      style={{
        paddingBottom: isMobile ? 104 : undefined,
        background: isMobile
          ? (isDark
            ? `linear-gradient(180deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[7]} 22%, transparent 42%)`
            : 'linear-gradient(180deg, #f8fafc 0%, #ffffff 22%, transparent 42%)')
          : undefined,
        minHeight: '100%',
      }}
    >
      <Stack gap="lg">
        {isMobile ? (
          <>
            <Group justify="space-between" mb="xs" align="flex-end" wrap="wrap" gap="xs">
              <Title order={4} fw={800}>Diagnosi</Title>
            </Group>
            <PortfolioSwitcher
              portfolios={portfolios}
              value={selectedPortfolioId}
              onChange={(nextValue) => setSelectedPortfolioId(nextValue)}
              loading={portfoliosLoading}
              style={{ width: '100%' }}
            />
          </>
        ) : (
          <Group justify="space-between" mb="md" align="flex-end" wrap="wrap" gap="xs">
            <Title order={2} fw={700}>Diagnosi</Title>
            <PortfolioSwitcher
              portfolios={portfolios}
              value={selectedPortfolioId}
              onChange={(nextValue) => setSelectedPortfolioId(nextValue)}
              loading={portfoliosLoading}
              style={{ width: '100%', maxWidth: 360 }}
            />
          </Group>
        )}

        {pageError && <Alert color="red">{pageError}</Alert>}

        {!selectedPortfolio && !portfoliosLoading && (
          <Alert color="yellow">
            Crea prima un portafoglio, poi torna qui per la diagnosi.
          </Alert>
        )}

        {healthLoading && portfolioId != null && (
          <Card withBorder radius="xl" padding="xl" style={{ background: cardBg, border: cardBorder }}>
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
                        <Text tt="uppercase" fw={800} size="xs" style={{ opacity: 0.72 }}>Diagnosi Portafoglio</Text>
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
                      <MetricChip label="Rischio" value={health.summary.risk_level} />
                      <MetricChip label="Diversificazione" value={health.summary.diversification} />
                      <MetricChip label="Sovrapposizione" value={health.summary.overlap} />
                      <MetricChip label="Costi" value={health.summary.cost_efficiency} />
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
                            {copied ? 'Riepilogo copiato' : 'Copia riepilogo'}
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
                            {copied ? 'Link copiato' : 'Copia link'}
                          </Button>
                        )}
                      </CopyButton>
                      <Badge variant="light" color="yellow" leftSection={<IconShare size={12} />}>
                        Pronta per la condivisione
                      </Badge>
                    </Group>
                  </Stack>
                </Card>
              </Grid.Col>

              <Grid.Col span={{ base: 12, xl: 4 }}>
                <Card withBorder radius="xl" padding="lg" h="100%" style={{ background: cardBg, border: cardBorder }}>
                  <Stack gap="md">
                    <Group gap="sm">
                      <ThemeIcon color="yellow" variant="light" radius="xl">
                        <IconSparkles size={18} />
                      </ThemeIcon>
                      <Title order={4}>Segnali principali</Title>
                    </Group>
                    {health.alerts.slice(0, 2).map((alert) => (
                      <Alert key={`${alert.type}-${alert.message}`} color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light">
                        {alert.message}
                      </Alert>
                    ))}
                    {!health.alerts.length && (
                      <Alert color="teal" variant="light">
                        Nessun avviso strutturale rilevante.
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
                <Card withBorder radius="xl" padding="lg" style={{ background: cardBg, border: cardBorder }}>
                  <Title order={4} mb="md">Dettaglio metriche</Title>
                  <Table withTableBorder withColumnBorders highlightOnHover>
                    <Table.Tbody>
                      <Table.Tr><Table.Td>Esposizione USA</Table.Td><Table.Td>{formatPct(health.metrics.geographic_exposure.usa)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Esposizione Europa</Table.Td><Table.Td>{formatPct(health.metrics.geographic_exposure.europe)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Esposizione emergenti</Table.Td><Table.Td>{formatPct(health.metrics.geographic_exposure.emerging)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Peso massimo posizione</Table.Td><Table.Td>{formatPct(health.metrics.max_position_weight)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Punteggio sovrapposizione</Table.Td><Table.Td>{formatPct(health.metrics.overlap_score)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>Volatilità</Table.Td><Table.Td>{formatPct(health.metrics.portfolio_volatility)}</Table.Td></Table.Tr>
                      <Table.Tr><Table.Td>TER ponderato</Table.Td><Table.Td>{formatPct(health.metrics.weighted_ter)}</Table.Td></Table.Tr>
                    </Table.Tbody>
                  </Table>
                </Card>
              </Grid.Col>

              <Grid.Col span={{ base: 12, lg: 6 }}>
                <Card withBorder radius="xl" padding="lg" style={{ background: cardBg, border: cardBorder }}>
                  <Title order={4} mb="md">Punteggi per categoria</Title>
                  <SimpleGrid cols={2} spacing="md">
                    <ScorePill label="Diversificazione" value={`${health.category_scores.diversification} / 25`} isDark={isDark} />
                    <ScorePill label="Rischio" value={`${health.category_scores.risk} / 25`} isDark={isDark} />
                    <ScorePill label="Concentrazione" value={`${health.category_scores.concentration} / 20`} isDark={isDark} />
                    <ScorePill label="Sovrapposizione" value={`${health.category_scores.overlap} / 15`} isDark={isDark} />
                    <ScorePill label="Efficienza costi" value={`${health.category_scores.cost_efficiency} / 15`} isDark={isDark} />
                  </SimpleGrid>
                </Card>
              </Grid.Col>
            </Grid>

            <Grid gutter="lg" align="start">
              <Grid.Col span={{ base: 12, lg: 6 }}>
                <Card withBorder radius="xl" padding="lg" style={{ background: cardBg, border: cardBorder }}>
                  <Group gap="sm" mb="md">
                    <ThemeIcon color="orange" variant="light" radius="xl">
                      <IconAlertTriangle size={18} />
                    </ThemeIcon>
                    <Title order={4}>Tutti gli avvisi</Title>
                  </Group>
                  <Stack gap="sm">
                    {health.alerts.length ? health.alerts.map((alert) => (
                      <Alert key={`${alert.type}-${alert.message}`} color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light">
                        {alert.message}
                      </Alert>
                    )) : <Text c="dimmed">Nessun avviso.</Text>}
                  </Stack>
                </Card>
              </Grid.Col>

              <Grid.Col span={{ base: 12, lg: 6 }}>
                <Card withBorder radius="xl" padding="lg" style={{ background: cardBg, border: cardBorder }}>
                  <Group gap="sm" mb="md">
                    <ThemeIcon color="teal" variant="light" radius="xl">
                      <IconSparkles size={18} />
                    </ThemeIcon>
                    <Title order={4}>Idee di miglioramento</Title>
                  </Group>
                  <Stack gap="sm">
                    {health.suggestions.length ? health.suggestions.map((suggestion) => (
                      <Alert key={suggestion.message} color="teal" variant="light">
                        {suggestion.message}
                      </Alert>
                    )) : <Text c="dimmed">Nessun suggerimento.</Text>}
                  </Stack>
                </Card>
              </Grid.Col>
            </Grid>
          </>
        )}
      </Stack>
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
