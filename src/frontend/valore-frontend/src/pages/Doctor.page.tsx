import { useEffect, useMemo, useRef, useState } from 'react';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import {
  ActionIcon,
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
  IconChartBubble,
  IconCheck,
  IconCopy,
  IconDownload,
  IconHeartRateMonitor,
  IconLink,
  IconRobot,
  IconShare,
  IconSparkles,
} from '@tabler/icons-react';
import { toBlob, toPng } from 'html-to-image';
import { CopilotChat } from '../components/copilot/CopilotChat';
import { PortfolioSwitcher } from '../components/portfolio/PortfolioSwitcher';
import { STORAGE_KEYS } from '../components/dashboard/constants';
import { usePortfolioHealth, usePortfolioSummary, usePortfolios } from '../components/dashboard/hooks/queries';
import { DoctorAlertDetailsModal } from '../components/doctor/DoctorAlertDetailsModal';
import { MonteCarloCard } from '../components/doctor/MonteCarloCard';
import { PageHeader } from '../components/layout/PageHeader';
import { PageLayout } from '../components/layout/PageLayout';
import { getCopilotStatus } from '../services/api';
import type { PortfolioHealthAlert } from '../services/api';

const PRIVACY_MASK = '******';

function isPrivacyModeEnabled(): boolean {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(STORAGE_KEYS.privacyModeEnabled) === 'true';
}

function scoreTone(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Eccellente', color: 'teal' };
  if (score >= 70) return { label: 'Buono', color: 'blue' };
  if (score >= 60) return { label: 'Nella media', color: 'yellow' };
  return { label: 'Debole', color: 'red' };
}

function formatPct(value: number | null | undefined): string {
  if (isPrivacyModeEnabled()) return PRIVACY_MASK;
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return `${value.toFixed(1)}%`;
}

function humanize(value: string): string {
  return value.replace(/_/g, ' ');
}

export function DoctorPage() {
  const isMobile = useMediaQuery('(max-width: 48em)');
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return window.localStorage.getItem(STORAGE_KEYS.selectedPortfolioId);
  });
  const [detailsAlert, setDetailsAlert] = useState<PortfolioHealthAlert | null>(null);
  const [copyImageState, setCopyImageState] = useState<'idle' | 'copying' | 'copied' | 'error'>('idle');
  const [copilotAvailable, setCopilotAvailable] = useState(false);
  const profileCardRef = useRef<HTMLDivElement | null>(null);
  const [copilotOpened, { open: openCopilot, close: closeCopilot }] = useDisclosure(false);

  const { data: portfolios = [], isLoading: portfoliosLoading, error: portfoliosError } = usePortfolios();
  const portfolioId = selectedPortfolioId ? Number(selectedPortfolioId) : null;
  const { data: health, isLoading: healthLoading, error: healthError } = usePortfolioHealth(portfolioId);
  const { data: summary } = usePortfolioSummary(portfolioId);

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

  useEffect(() => {
    getCopilotStatus().then((status) => setCopilotAvailable(status.available)).catch(() => {});
  }, []);

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
      `Rischio: ${humanize(health.summary.risk_level)}`,
      `Diversificazione: ${humanize(health.summary.diversification)}`,
      `Sovrapposizione: ${humanize(health.summary.overlap)}`,
      `Costi: ${humanize(health.summary.cost_efficiency)}`,
      alerts ? `Avvisi:\n${alerts}` : '',
      suggestions ? `Suggerimenti:\n${suggestions}` : '',
    ].filter(Boolean).join('\n');
  }, [health, selectedPortfolio]);

  const tone = scoreTone(health?.score ?? 0);
  const pageError = (portfoliosError instanceof Error ? portfoliosError.message : null)
    || (healthError instanceof Error ? healthError.message : null);
  const baseCurrency = selectedPortfolio?.base_currency ?? summary?.base_currency ?? 'EUR';
  const doctorQuickPrompts = useMemo(() => ([
    'Spiega il punteggio Doctor in modo operativo',
    'Quali sono i 3 rischi principali di questo portafoglio?',
    'Come ridurresti la concentrazione senza stravolgere il portafoglio?',
    'Interpretami overlap, volatilita e costi',
    'Dimmi un piano d azione in 30 giorni basato sul report Doctor',
    `Riassumi il referto Doctor di ${selectedPortfolio?.name ?? 'questo portafoglio'}`,
  ]), [selectedPortfolio?.name]);

  async function handleCopyProfileImage() {
    if (!profileCardRef.current || typeof window === 'undefined') {
      setCopyImageState('error');
      return;
    }

    try {
      setCopyImageState('copying');
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);

      // Strategy 1: Web Share API (works on Mobile Safari / iOS)
      if (navigator.share && /iPhone|iPad|iPod|Android/i.test(navigator.userAgent)) {
        const dataUrl = await toPng(profileCardRef.current, { cacheBust: true, pixelRatio });
        const res = await fetch(dataUrl);
        const blob = await res.blob();
        const file = new File([blob], 'doctor-report.png', { type: 'image/png' });

        if (navigator.canShare?.({ files: [file] })) {
          await navigator.share({ files: [file], title: 'Portfolio Doctor' });
          setCopyImageState('copied');
          window.setTimeout(() => setCopyImageState('idle'), 2000);
          return;
        }
      }

      // Strategy 2: Clipboard API (desktop browsers)
      if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
        const blob = await toBlob(profileCardRef.current, { cacheBust: true, pixelRatio });
        if (!blob) throw new Error('Image export failed');
        await navigator.clipboard.write([
          new ClipboardItem({ [blob.type || 'image/png']: blob }),
        ]);
        setCopyImageState('copied');
        window.setTimeout(() => setCopyImageState('idle'), 2000);
        return;
      }

      // Strategy 3: Download fallback (any browser)
      const dataUrl = await toPng(profileCardRef.current, { cacheBust: true, pixelRatio });
      const link = document.createElement('a');
      link.download = 'doctor-report.png';
      link.href = dataUrl;
      link.click();
      setCopyImageState('copied');
      window.setTimeout(() => setCopyImageState('idle'), 2000);
    } catch {
      setCopyImageState('error');
      window.setTimeout(() => setCopyImageState('idle'), 2500);
    }
  }

  return (
    <PageLayout variant="editorial">
      <Container fluid>
        <Stack gap="lg">
          <PageHeader
            eyebrow="Diagnostica pronta da condividere"
            title="Doctor"
            description="Un checkup del portafoglio progettato per essere leggibile, adatto agli screenshot e pronto da condividere."
            actions={(
              <PortfolioSwitcher
                portfolios={portfolios}
                value={selectedPortfolioId}
                onChange={(nextValue) => setSelectedPortfolioId(nextValue)}
                loading={portfoliosLoading}
                style={{ width: '100%', maxWidth: 360 }}
              />
            )}
          />

          {pageError && <Alert color="red">{pageError}</Alert>}

          {!selectedPortfolio && !portfoliosLoading && (
            <Alert color="yellow">
              Crea prima un portafoglio, poi torna qui per un report del Doctor.
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
                    ref={profileCardRef}
                    radius="xl"
                    padding={{ base: 'md', sm: 'xl' }}
                    withBorder
                    style={{ background: 'linear-gradient(140deg, #103c39 0%, #1f5d59 58%, #f0b24f 160%)', color: 'white', overflow: 'hidden' }}
                  >
                    <Stack gap="lg">
                      <Group justify="space-between" align="flex-start" wrap="wrap">
                        <div>
                          <Text tt="uppercase" fw={800} size="xs" style={{ opacity: 0.72 }}>Portfolio Doctor</Text>
                          <Title order={1} mt={6} c="white" style={{ fontSize: 'clamp(3rem, 7vw, 5.5rem)', lineHeight: 0.95 }}>
                            {isPrivacyModeEnabled() ? PRIVACY_MASK : health.score}
                            {!isPrivacyModeEnabled() && <Text component="span" inherit style={{ opacity: 0.72 }}> / 100</Text>}
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
                        <Button
                          variant="outline"
                          color="gray"
                          leftSection={copyImageState === 'copied' ? <IconCheck size={16} /> : <IconShare size={16} />}
                          onClick={handleCopyProfileImage}
                          radius="xl"
                          loading={copyImageState === 'copying'}
                        >
                          {copyImageState === 'copied'
                            ? 'Fatto!'
                            : copyImageState === 'error'
                              ? 'Non disponibile'
                              : 'Condividi immagine'}
                        </Button>
                        {copilotAvailable && (
                          <Button
                            variant="light"
                            color="teal"
                            leftSection={<IconRobot size={16} />}
                            onClick={openCopilot}
                            radius="xl"
                          >
                            Apri Doctor Copilot
                          </Button>
                        )}
                        <Badge variant="light" color="yellow" leftSection={<IconShare size={12} />} style={{ whiteSpace: 'normal', height: 'auto', lineHeight: 1.4 }}>
                          Pensato per la condivisione via screenshot
                        </Badge>
                      </Group>
                    </Stack>
                  </Card>
                </Grid.Col>

                <Grid.Col span={{ base: 12, xl: 4 }}>
                  <Card withBorder radius="xl" padding="lg" h="100%" style={{ overflow: 'hidden' }}>
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
                          Nessun avviso strutturale rilevante rilevato.
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
                    <Title order={4} mb="md">Dettaglio metriche</Title>
                    <Table withTableBorder withColumnBorders highlightOnHover style={{ tableLayout: 'fixed' }}>
                      <Table.Tbody>
                        <Table.Tr><Table.Td style={{ wordBreak: 'break-word' }}>Esposizione USA</Table.Td><Table.Td>{formatPct(health.metrics.geographic_exposure.usa)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td style={{ wordBreak: 'break-word' }}>Esposizione Europa</Table.Td><Table.Td>{formatPct(health.metrics.geographic_exposure.europe)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td style={{ wordBreak: 'break-word' }}>Esposizione Emergenti</Table.Td><Table.Td>{formatPct(health.metrics.geographic_exposure.emerging)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td style={{ wordBreak: 'break-word' }}>Peso max posizione</Table.Td><Table.Td>{formatPct(health.metrics.max_position_weight)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td style={{ wordBreak: 'break-word' }}>Sovrapposizione</Table.Td><Table.Td>{formatPct(health.metrics.overlap_score)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td style={{ wordBreak: 'break-word' }}>Volatilità</Table.Td><Table.Td>{formatPct(health.metrics.portfolio_volatility)}</Table.Td></Table.Tr>
                        <Table.Tr><Table.Td style={{ wordBreak: 'break-word' }}>TER ponderato</Table.Td><Table.Td>{formatPct(health.metrics.weighted_ter)}</Table.Td></Table.Tr>
                      </Table.Tbody>
                    </Table>
                  </Card>
                </Grid.Col>

                <Grid.Col span={{ base: 12, lg: 6 }}>
                  <Card withBorder radius="xl" padding="lg">
                    <Title order={4} mb="md">Punteggi per categoria</Title>
                    <SimpleGrid cols={2} spacing="md">
                      <ScorePill label="Diversificazione" value={isPrivacyModeEnabled() ? PRIVACY_MASK : `${health.category_scores.diversification} / 25`} />
                      <ScorePill label="Rischio" value={isPrivacyModeEnabled() ? PRIVACY_MASK : `${health.category_scores.risk} / 25`} />
                      <ScorePill label="Concentrazione" value={isPrivacyModeEnabled() ? PRIVACY_MASK : `${health.category_scores.concentration} / 20`} />
                      <ScorePill label="Sovrapposizione" value={isPrivacyModeEnabled() ? PRIVACY_MASK : `${health.category_scores.overlap} / 15`} />
                      <ScorePill label="Efficienza costi" value={isPrivacyModeEnabled() ? PRIVACY_MASK : `${health.category_scores.cost_efficiency} / 15`} />
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
                      <Title order={4}>Tutti gli avvisi</Title>
                    </Group>
                    <Stack gap="sm">
                      {health.alerts.length ? health.alerts.map((alert) => (
                        <Alert key={`${alert.type}-${alert.message}`} color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light">
                          <Group justify="space-between" align="center" wrap="wrap" gap="sm">
                            <Text>{alert.message}</Text>
                            {alert.details && (
                              <Button
                                variant="subtle"
                                size="xs"
                                color={alert.severity === 'critical' ? 'red' : 'orange'}
                                leftSection={<IconChartBubble size={14} />}
                                onClick={() => setDetailsAlert(alert)}
                              >
                                Approfondisci
                              </Button>
                            )}
                          </Group>
                        </Alert>
                      )) : <Text c="dimmed">Nessun avviso.</Text>}
                    </Stack>
                  </Card>
                </Grid.Col>

                <Grid.Col span={{ base: 12, lg: 6 }}>
                  <Card withBorder radius="xl" padding="lg">
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

              <MonteCarloCard
                portfolioId={portfolioId}
                marketValue={summary?.market_value ?? null}
                currency={summary?.base_currency ?? 'EUR'}
              />

              <DoctorAlertDetailsModal
                alert={detailsAlert}
                opened={detailsAlert != null}
                onClose={() => setDetailsAlert(null)}
                currency={baseCurrency}
              />
            </>
          )}
        </Stack>
      </Container>

      {copilotAvailable && (
        <ActionIcon
          variant="filled"
          color="teal"
          size={52}
          radius="xl"
          onClick={openCopilot}
          aria-label="Apri Doctor Copilot"
          style={{
            position: 'fixed',
            bottom: isMobile ? 24 : 24,
            right: 24,
            zIndex: 100,
            boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
          }}
        >
          <IconRobot size={24} />
        </ActionIcon>
      )}

      <CopilotChat
        opened={copilotOpened}
        onClose={closeCopilot}
        portfolioId={portfolioId}
        title="Doctor Copilot"
        quickPrompts={doctorQuickPrompts}
        emptyStateDescription="Interpreto il referto Doctor, spiego rischi e priorita operative del portafoglio."
      />
    </PageLayout>
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
      <Text size="xs" tt="uppercase" style={{ opacity: 0.7, wordBreak: 'break-word' }}>{label}</Text>
      <Text fw={700} style={{ wordBreak: 'break-word' }}>{humanize(value)}</Text>
    </Box>
  );
}

function ScorePill({ label, value }: { label: string; value: string }) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

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
      <Text size="sm" c="dimmed">{label}</Text>
      <Text fw={800} size="lg">{value}</Text>
    </Box>
  );
}
