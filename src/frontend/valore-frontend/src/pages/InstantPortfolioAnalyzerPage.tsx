import { useEffect, useState } from 'react';
import { Box, Button, Container, Grid, Group, Progress, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { SignInButton, SignUpButton, SignedIn, SignedOut } from '@clerk/clerk-react';
import {
  IconArrowRight,
  IconBolt,
  IconChartDonut3,
  IconClockHour4,
  IconLock,
  IconShieldCheck,
  IconSparkles,
  IconTargetArrow,
} from '@tabler/icons-react';
import logoMark from '../assets/logo-mark.svg';
import { InstantAnalyzerForm } from '../components/instant-analyzer/InstantAnalyzerForm';
import { InstantAnalyzerInputIssues } from '../components/instant-analyzer/InstantAnalyzerInputIssues';
import { InstantAnalyzerResults } from '../components/instant-analyzer/InstantAnalyzerResults';
import {
  ApiRequestError,
  analyzeInstantPortfolio,
  importInstantPortfolioCsv,
  type InstantAnalyzeLineError,
  type InstantAnalyzeResponse,
  type InstantAnalyzeUnresolvedItem,
} from '../services/api';
import type { ManualPositionDraft } from '../components/instant-analyzer/InstantAnalyzerForm';

function createManualPosition(): ManualPositionDraft {
  return {
    id: Math.random().toString(36).slice(2, 10),
    identifier: '',
    value: '',
  };
}

function buildRawTextFromManualPositions(positions: ManualPositionDraft[]): string {
  return positions
    .map((position) => {
      const identifier = position.identifier.trim().toUpperCase();
      const value = position.value.trim();
      if (!identifier || !value) return '';
      return `${identifier} ${value}`;
    })
    .filter(Boolean)
    .join('\n');
}

interface InstantAnalyzerErrorDetails {
  parseErrors: InstantAnalyzeLineError[];
  unresolved: InstantAnalyzeUnresolvedItem[];
}

function readErrorDetails(error: unknown): InstantAnalyzerErrorDetails {
  if (!(error instanceof ApiRequestError) || !error.details) {
    return { parseErrors: [], unresolved: [] };
  }

  const parseErrors = Array.isArray(error.details.parse_errors)
    ? (error.details.parse_errors as InstantAnalyzeLineError[])
    : [];
  const unresolved = Array.isArray(error.details.unresolved)
    ? (error.details.unresolved as InstantAnalyzeUnresolvedItem[])
    : [];

  return { parseErrors, unresolved };
}

const STEPS = [
  {
    number: '1',
    title: 'Login',
    description: 'Accedi con Google o email se vuoi importare e salvare il portafoglio.',
    icon: IconSparkles,
  },
  {
    number: '2',
    title: 'Import',
    description: 'Manuale, CSV in app o demo immediata per vedere il risultato in pochi secondi.',
    icon: IconBolt,
  },
  {
    number: '3',
    title: 'Analisi',
    description: 'Il motore controlla concentrazione geografica, overlap e rischio.',
    icon: IconChartDonut3,
  },
  {
    number: '4',
    title: 'Top insight',
    description: 'Ricevi al massimo 3 insight, ordinati per priorita e facili da capire.',
    icon: IconChartDonut3,
  },
  {
    number: '5',
    title: 'AI Explain',
    description: 'Ogni insight puo essere spiegato con un linguaggio semplice e non operativo.',
    icon: IconChartDonut3,
  },
];

const TRUST_FEATURES = [
  {
    icon: IconClockHour4,
    title: 'Meno di 2 minuti',
    description: 'Dal primo input ai 3 insight principali con un percorso molto breve.',
  },
  {
    icon: IconLock,
    title: 'Login rapido',
    description: 'Google o email in pochi secondi se vuoi salvare o importare in modo persistente.',
  },
  {
    icon: IconShieldCheck,
    title: 'Privacy first',
    description: 'La demo pubblica resta anonima e non salva il portafoglio.',
  },
  {
    icon: IconTargetArrow,
    title: 'Score 0–100',
    description: 'Un punteggio chiaro per capire subito la salute del portafoglio.',
  },
];

const LOADING_MESSAGES = [
  'Sto normalizzando le posizioni del portafoglio...',
  'Controllo la concentrazione geografica dominante...',
  'Cerco eventuali sovrapposizioni tra holdings sottostanti...',
  'Stimo rischio e drawdown del mix complessivo...',
  'Ordino gli insight per mostrarti solo quelli piu importanti...',
];

const clerkEnabled = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

export function InstantPortfolioAnalyzerPage() {
  const [rawText, setRawText] = useState('VWCE 10000\nAGGH 5000\nEIMI 2000');
  const [inputMode, setInputMode] = useState<'demo' | 'manual' | 'csv'>('demo');
  const [manualPositions, setManualPositions] = useState<ManualPositionDraft[]>([
    createManualPosition(),
    createManualPosition(),
  ]);
  const [csvImporting, setCsvImporting] = useState(false);
  const [csvSummary, setCsvSummary] = useState<string | null>(null);
  const [csvFileName, setCsvFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingStepIndex, setLoadingStepIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InstantAnalyzeResponse | null>(null);
  const [errorDetails, setErrorDetails] = useState<InstantAnalyzerErrorDetails>({ parseErrors: [], unresolved: [] });

  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');
  const sectionPx = isMobile ? 'xs' : 'xl';

  const emerald = '#10b981';
  const emeraldDark = '#059669';
  const emeraldLight = '#ecfdf5';
  const emeraldBorder = '#a7f3d0';

  useEffect(() => {
    if (!loading) {
      setLoadingStepIndex(0);
      return;
    }

    const timer = window.setInterval(() => {
      setLoadingStepIndex((current) => (current + 1) % LOADING_MESSAGES.length);
    }, 900);

    return () => window.clearInterval(timer);
  }, [loading]);

  const handleSubmit = async () => {
    const payloadText = inputMode === 'manual'
      ? buildRawTextFromManualPositions(manualPositions)
      : rawText;

    if (!payloadText.trim()) {
      setError(
        inputMode === 'manual'
          ? 'Inserisci almeno una posizione manuale prima di avviare l\'analisi.'
          : 'Incolla almeno una posizione prima di avviare l\'analisi.',
      );
      setErrorDetails({ parseErrors: [], unresolved: [] });
      return;
    }

    if (inputMode === 'manual') {
      setRawText(payloadText);
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setErrorDetails({ parseErrors: [], unresolved: [] });
    try {
      const response = await analyzeInstantPortfolio({ input_mode: 'raw_text', raw_text: payloadText });
      setResult(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Impossibile analizzare questo portafoglio in questo momento.');
      setResult(null);
      setErrorDetails(readErrorDetails(requestError));
    } finally {
      setLoading(false);
    }
  };

  const handleCsvFileSelect = async (file: File | null) => {
    if (!file) return;
    setCsvImporting(true);
    setError(null);
    setErrorDetails({ parseErrors: [], unresolved: [] });
    try {
      const response = await importInstantPortfolioCsv(file, 'fineco');
      setCsvFileName(response.filename);
      setCsvSummary(
        `${response.positions.length} posizioni ricostruite da ${response.valid_rows} righe valide`
        + (response.error_rows > 0 ? `, ${response.error_rows} righe con problemi.` : '.'),
      );
      setRawText(response.raw_text);
      setInputMode('csv');
      setErrorDetails({ parseErrors: response.parse_errors, unresolved: [] });
    } catch (requestError) {
      setCsvSummary(null);
      setCsvFileName(file.name);
      setError(requestError instanceof Error ? requestError.message : 'Impossibile importare il file CSV.');
    } finally {
      setCsvImporting(false);
    }
  };

  return (
    <Box style={{ minHeight: '100vh', background: isDark ? theme.colors.dark[8] : '#ffffff' }}>
      {/* ─── Navigation bar ─── */}
      <Box
        component="header"
        style={{
          borderBottom: isDark ? `1px solid ${theme.colors.dark[5]}` : '1px solid #e5e7eb',
          background: isDark ? theme.colors.dark[7] : 'rgba(255,255,255,0.85)',
          backdropFilter: 'blur(12px)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        <Container size="1200" px={sectionPx}>
          <Group justify="space-between" h={64}>
            <Group gap="sm" wrap="nowrap">
              <Box
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  background: isDark ? theme.colors.dark[5] : emeraldLight,
                  border: isDark ? `1px solid ${theme.colors.dark[4]}` : `1px solid ${emeraldBorder}`,
                  padding: 4,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <img src={logoMark} alt="Valore365" style={{ width: 24, height: 24 }} />
              </Box>
              <Text fw={800} size="lg" c={isDark ? 'white' : '#111827'}>
                Valore365
              </Text>
            </Group>
            <Group
              gap={8}
              style={{
                background: isDark ? theme.colors.dark[5] : emeraldLight,
                border: isDark ? `1px solid ${theme.colors.dark[4]}` : `1px solid ${emeraldBorder}`,
                borderRadius: 999,
                padding: '6px 14px',
              }}
            >
              <Box style={{ width: 8, height: 8, borderRadius: '50%', background: emerald }} />
              <Text size="sm" fw={600} c={isDark ? theme.colors.teal[3] : emeraldDark}>
                Instant Analyzer
              </Text>
            </Group>
          </Group>
        </Container>
      </Box>

      {/* ─── Hero section ─── */}
      <Box
        style={{
          background: isDark
            ? theme.colors.dark[8]
            : 'linear-gradient(180deg, #f0fdf4 0%, #ffffff 100%)',
          paddingTop: isMobile ? 48 : 80,
          paddingBottom: isMobile ? 40 : 64,
        }}
      >
        <Container size="1200" px={sectionPx}>
          <Stack gap="xl" align="center" style={{ textAlign: 'center' }}>
            <Group
              gap={6}
              style={{
                background: isDark ? 'rgba(16, 185, 129, 0.1)' : 'rgba(16, 185, 129, 0.08)',
                border: isDark ? `1px solid rgba(16, 185, 129, 0.2)` : `1px solid ${emeraldBorder}`,
                borderRadius: 999,
                padding: '6px 16px',
              }}
            >
              <IconSparkles size={16} color={emerald} />
              <Text fw={700} size="sm" c={isDark ? theme.colors.teal[3] : emeraldDark}>
                Analisi gratuita e istantanea
              </Text>
            </Group>

            <Title
              order={1}
              c={isDark ? 'white' : '#111827'}
              style={{
                fontSize: isMobile ? '2rem' : 'clamp(2.8rem, 5vw, 3.8rem)',
                lineHeight: 1.1,
                letterSpacing: '-0.03em',
                maxWidth: 800,
              }}
            >
              Controlla la salute del tuo{' '}
              <Text span c={emerald} inherit>
                portafoglio
              </Text>{' '}
              in 30 secondi
            </Title>

            <Text
              size={isMobile ? 'md' : 'lg'}
              c={isDark ? theme.colors.gray[4] : '#374151'}
              maw={620}
              style={{ lineHeight: 1.6 }}
            >
              Capisci i problemi principali del tuo portafoglio in meno di due minuti:
              fino a 3 insight chiari, semplici e spiegabili.
            </Text>

            <Group gap="lg" wrap="wrap" justify="center">
              {[
                { icon: IconTargetArrow, text: '3 insight prioritizzati' },
                { icon: IconShieldCheck, text: 'Modalita demo immediata' },
              ].map(({ icon: Icon, text }) => (
                <Group key={text} gap={8}>
                  <ThemeIcon color="teal" variant="light" radius="xl" size="sm">
                    <Icon size={14} />
                  </ThemeIcon>
                  <Text fw={600} size="sm" c={isDark ? theme.colors.gray[3] : '#374151'}>
                    {text}
                  </Text>
                </Group>
              ))}
            </Group>

            <Group gap="sm" wrap="wrap" justify="center">
              {clerkEnabled ? (
                <SignedOut>
                  <SignUpButton mode="modal" forceRedirectUrl="/portfolio" fallbackRedirectUrl="/portfolio">
                    <Button
                      radius="md"
                      size="md"
                      rightSection={<IconArrowRight size={16} />}
                      style={{
                        background: `linear-gradient(135deg, ${emerald} 0%, ${emeraldDark} 100%)`,
                        border: 'none',
                        fontWeight: 700,
                      }}
                    >
                      Accedi e importa il portafoglio
                    </Button>
                  </SignUpButton>
                </SignedOut>
              ) : (
                <Button
                  component="a"
                  href="/portfolio"
                  radius="md"
                  size="md"
                  rightSection={<IconArrowRight size={16} />}
                  style={{
                    background: `linear-gradient(135deg, ${emerald} 0%, ${emeraldDark} 100%)`,
                    border: 'none',
                    fontWeight: 700,
                  }}
                >
                  Accedi e importa il portafoglio
                </Button>
              )}
              {clerkEnabled && (
                <SignedIn>
                  <Button
                    component="a"
                    href="/portfolio"
                    radius="md"
                    size="md"
                    rightSection={<IconArrowRight size={16} />}
                    style={{
                      background: `linear-gradient(135deg, ${emerald} 0%, ${emeraldDark} 100%)`,
                      border: 'none',
                      fontWeight: 700,
                    }}
                  >
                    Vai al portfolio
                  </Button>
                </SignedIn>
              )}
              <Button
                variant="light"
                radius="md"
                size="md"
                onClick={() => {
                  setInputMode('demo');
                  setRawText('VWCE 10000\nAGGH 5000\nEIMI 2000');
                  window.scrollTo({ top: 820, behavior: 'smooth' });
                }}
              >
                Prova la demo
              </Button>
            </Group>
          </Stack>
        </Container>
      </Box>

      {/* ─── How it works ─── */}
      <Box
        style={{
          background: isDark ? theme.colors.dark[7] : '#ffffff',
          borderTop: isDark ? `1px solid ${theme.colors.dark[5]}` : '1px solid #f3f4f6',
          borderBottom: isDark ? `1px solid ${theme.colors.dark[5]}` : '1px solid #f3f4f6',
          padding: isMobile ? '40px 0' : '64px 0',
        }}
      >
        <Container size="1200" px={sectionPx}>
          <Stack gap="xl">
            <Stack gap={4} align="center" style={{ textAlign: 'center' }}>
              <Text tt="uppercase" fw={800} size="xs" c={emerald} style={{ letterSpacing: '0.05em' }}>
                Come funziona
              </Text>
              <Title order={2} c={isDark ? 'white' : '#111827'} style={{ fontSize: isMobile ? '1.5rem' : '2rem' }}>
                Un percorso rapido, zero frizione inutile
              </Title>
            </Stack>

            <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }} spacing="xl">
              {STEPS.map((step) => (
                <Stack
                  key={step.number}
                  gap="md"
                  align="center"
                  style={{
                    textAlign: 'center',
                    padding: isMobile ? 20 : 28,
                    borderRadius: 16,
                    border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
                    background: isDark ? theme.colors.dark[6] : '#ffffff',
                    transition: 'all 300ms ease',
                  }}
                >
                  <Box
                    style={{
                      width: 52,
                      height: 52,
                      borderRadius: '50%',
                      background: isDark ? 'rgba(16, 185, 129, 0.12)' : emeraldLight,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <step.icon size={24} color={emerald} />
                  </Box>
                  <Stack gap={4}>
                    <Text fw={700} size="sm" c={emerald}>
                      Step {step.number}
                    </Text>
                    <Text fw={700} c={isDark ? 'white' : '#111827'}>
                      {step.title}
                    </Text>
                    <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
                      {step.description}
                    </Text>
                  </Stack>
                </Stack>
              ))}
            </SimpleGrid>
          </Stack>
        </Container>
      </Box>

      {/* ─── Main content: Form + Results ─── */}
      <Box
        style={{
          background: isDark ? theme.colors.dark[8] : '#f9fafb',
          padding: isMobile ? '40px 0 48px' : '64px 0 80px',
        }}
      >
        <Container size="1200" px={sectionPx}>
          <Stack gap="xl">
            <Box
              style={{
                borderRadius: 20,
                border: isDark ? `1px solid ${theme.colors.dark[4]}` : `1px solid ${emeraldBorder}`,
                background: isDark
                  ? `linear-gradient(135deg, ${theme.colors.dark[6]} 0%, rgba(16, 185, 129, 0.12) 100%)`
                  : 'linear-gradient(135deg, #ffffff 0%, #ecfdf5 100%)',
                padding: isMobile ? 20 : 28,
              }}
            >
              <Stack gap="md">
                <Group gap="xs">
                  <ThemeIcon color="teal" variant="light" radius="xl">
                    <IconLock size={16} />
                  </ThemeIcon>
                  <Text tt="uppercase" fw={800} size="xs" c={emerald} style={{ letterSpacing: '0.05em' }}>
                    Step 1 attivo
                  </Text>
                </Group>

                <Title order={3} c={isDark ? 'white' : '#111827'} style={{ fontSize: isMobile ? '1.25rem' : '1.5rem' }}>
                  Login veloce per importare e salvare il portafoglio
                </Title>

                <Text size="sm" c={isDark ? theme.colors.gray[4] : '#4b5563'} maw={720}>
                  Se vuoi un percorso completo con portfolio persistente, entra con Google o email.
                  Se preferisci, puoi comunque continuare sotto con demo, inserimento manuale o CSV Fineco senza salvare nulla.
                </Text>

                {clerkEnabled ? (
                  <>
                    <SignedOut>
                      <Group gap="sm" wrap="wrap">
                        <SignInButton mode="modal" forceRedirectUrl="/portfolio" fallbackRedirectUrl="/portfolio">
                          <Button radius="md" size="md" rightSection={<IconArrowRight size={16} />}>
                            Accedi con Google o email
                          </Button>
                        </SignInButton>
                        <SignUpButton mode="modal" forceRedirectUrl="/portfolio" fallbackRedirectUrl="/portfolio">
                          <Button variant="default" radius="md" size="md">
                            Crea account gratis
                          </Button>
                        </SignUpButton>
                      </Group>
                    </SignedOut>

                    <SignedIn>
                      <Group gap="sm" wrap="wrap">
                        <Button component="a" href="/portfolio" radius="md" size="md" rightSection={<IconArrowRight size={16} />}>
                          Vai al portfolio
                        </Button>
                        <Button
                          variant="light"
                          radius="md"
                          size="md"
                          onClick={() => window.scrollTo({ top: 1280, behavior: 'smooth' })}
                        >
                          Continua con l&apos;analyzer pubblico
                        </Button>
                      </Group>
                    </SignedIn>
                  </>
                ) : (
                  <Group gap="sm" wrap="wrap">
                    <Button component="a" href="/portfolio" radius="md" size="md" rightSection={<IconArrowRight size={16} />}>
                      Apri il portfolio
                    </Button>
                    <Button
                      variant="light"
                      radius="md"
                      size="md"
                      onClick={() => window.scrollTo({ top: 1280, behavior: 'smooth' })}
                    >
                      Continua con l&apos;analyzer pubblico
                    </Button>
                  </Group>
                )}
              </Stack>
            </Box>

            <Stack gap={4} align="center" style={{ textAlign: 'center' }}>
              <Text tt="uppercase" fw={800} size="xs" c={emerald} style={{ letterSpacing: '0.05em' }}>
                Prova subito
              </Text>
              <Title order={2} c={isDark ? 'white' : '#111827'} style={{ fontSize: isMobile ? '1.5rem' : '2rem' }}>
                Demo mode: analizza il portafoglio
              </Title>
              <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'} maw={620}>
                Puoi usare demo, inserimento manuale minimo o upload Fineco. L&apos;account serve solo se vuoi salvare il portafoglio in modo permanente.
              </Text>
            </Stack>

            <Grid gutter="xl" align="start">
              <Grid.Col span={{ base: 12, lg: 5 }}>
                <InstantAnalyzerForm
                  mode={inputMode}
                  value={rawText}
                  error={error}
                  loading={loading}
                  csvImporting={csvImporting}
                  csvSummary={csvSummary}
                  csvFileName={csvFileName}
                  onModeChange={setInputMode}
                  onChange={setRawText}
                  onSubmit={handleSubmit}
                  onSelectExample={(example) => {
                    setInputMode('demo');
                    setRawText(example);
                  }}
                  manualPositions={manualPositions}
                  onManualChange={(id, field, value) => {
                    setManualPositions((current) => current.map((position) => (
                      position.id === id ? { ...position, [field]: value } : position
                    )));
                  }}
                  onManualAdd={() => setManualPositions((current) => [...current, createManualPosition()])}
                  onManualRemove={(id) => {
                    setManualPositions((current) => {
                      if (current.length === 1) return current;
                      return current.filter((position) => position.id !== id);
                    });
                  }}
                  onCsvFileSelect={(file) => { void handleCsvFileSelect(file); }}
                  onReset={() => {
                    setInputMode('demo');
                    setRawText('');
                    setManualPositions([createManualPosition(), createManualPosition()]);
                    setCsvSummary(null);
                    setCsvFileName(null);
                    setResult(null);
                    setError(null);
                    setErrorDetails({ parseErrors: [], unresolved: [] });
                  }}
                />
              </Grid.Col>

              <Grid.Col span={{ base: 12, lg: 7 }}>
                {loading ? (
                  <Box
                    style={{
                      padding: isMobile ? 20 : 28,
                      borderRadius: 16,
                      border: isDark ? `1px solid ${theme.colors.dark[4]}` : `1px solid ${emeraldBorder}`,
                      background: isDark ? theme.colors.dark[6] : '#ffffff',
                      boxShadow: isDark ? 'none' : '0 1px 3px rgba(0,0,0,0.04)',
                    }}
                  >
                    <Stack gap="lg">
                      <div>
                        <Text tt="uppercase" fw={800} size="xs" c={emerald} style={{ letterSpacing: '0.05em' }}>
                          Step 3 · Analisi in corso
                        </Text>
                        <Title order={3} c={isDark ? 'white' : '#111827'} mt={4}>
                          Stiamo analizzando il tuo portafoglio...
                        </Title>
                      </div>
                      <Progress
                        value={Math.max(18, ((loadingStepIndex + 1) / LOADING_MESSAGES.length) * 100)}
                        color="teal"
                        radius="xl"
                        size="lg"
                        animated
                      />
                      <Stack gap="xs">
                        {LOADING_MESSAGES.map((message, index) => (
                          <Group key={message} gap="sm" wrap="nowrap">
                            <Box
                              style={{
                                width: 10,
                                height: 10,
                                borderRadius: '50%',
                                background: index <= loadingStepIndex ? emerald : (isDark ? theme.colors.dark[4] : '#d1d5db'),
                                flexShrink: 0,
                              }}
                            />
                            <Text
                              size="sm"
                              c={index <= loadingStepIndex ? (isDark ? 'white' : '#111827') : (isDark ? theme.colors.gray[5] : '#9ca3af')}
                            >
                              {message}
                            </Text>
                          </Group>
                        ))}
                      </Stack>
                    </Stack>
                  </Box>
                ) : result ? (
                  <InstantAnalyzerResults result={result} />
                ) : (
                  <Stack gap="lg">
                    <Box
                      style={{
                        padding: isMobile ? 20 : 28,
                        borderRadius: 16,
                        border: isDark ? `1px solid ${theme.colors.dark[4]}` : `1px solid ${emeraldBorder}`,
                        background: isDark ? theme.colors.dark[6] : emeraldLight,
                      }}
                    >
                      <Group gap="sm" mb="sm">
                        <ThemeIcon color="teal" variant="light" radius="xl" size="md">
                          <IconArrowRight size={16} />
                        </ThemeIcon>
                        <Text fw={700} c={isDark ? 'white' : '#111827'}>
                          Cosa otterrai
                        </Text>
                      </Group>
                      <Stack gap={8}>
                        {[
                          'Massimo 3 insight principali, gia ordinati per priorita',
                          'Titolo chiaro e descrizione breve per ogni problema rilevante',
                          'Spiegazione semplice on demand con CTA “Spiegamelo meglio”',
                          'Metriche di supporto su geografia, overlap, drawdown e allocazione',
                          'Demo immediata per capire se vale la pena fare login e import completo',
                        ].map((item) => (
                          <Group key={item} gap={8} wrap="nowrap">
                            <Box
                              style={{
                                width: 6,
                                height: 6,
                                borderRadius: '50%',
                                background: emerald,
                                flexShrink: 0,
                              }}
                            />
                            <Text size="sm" c={isDark ? theme.colors.gray[3] : '#374151'}>
                              {item}
                            </Text>
                          </Group>
                        ))}
                      </Stack>
                    </Box>
                    <InstantAnalyzerInputIssues
                      parseErrors={errorDetails.parseErrors}
                      unresolved={errorDetails.unresolved}
                    />
                  </Stack>
                )}
              </Grid.Col>
            </Grid>
          </Stack>
        </Container>
      </Box>

      {/* ─── Trust features ─── */}
      <Box
        style={{
          background: isDark ? theme.colors.dark[7] : '#ffffff',
          borderTop: isDark ? `1px solid ${theme.colors.dark[5]}` : '1px solid #f3f4f6',
          padding: isMobile ? '40px 0' : '64px 0',
        }}
      >
        <Container size="1200" px={sectionPx}>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="xl">
            {TRUST_FEATURES.map((feature) => (
              <Stack
                key={feature.title}
                gap="sm"
                style={{
                  padding: isMobile ? 20 : 24,
                  borderRadius: 16,
                  border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
                  background: isDark ? theme.colors.dark[6] : '#ffffff',
                  transition: 'all 300ms ease',
                }}
              >
                <Box
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: '50%',
                    background: isDark ? 'rgba(16, 185, 129, 0.12)' : emeraldLight,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <feature.icon size={22} color={emerald} />
                </Box>
                <Text fw={700} c={isDark ? 'white' : '#111827'}>
                  {feature.title}
                </Text>
                <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
                  {feature.description}
                </Text>
              </Stack>
            ))}
          </SimpleGrid>
        </Container>
      </Box>

      {/* ─── Footer ─── */}
      <Box
        component="footer"
        style={{
          background: isDark ? theme.colors.dark[9] : '#111827',
          padding: isMobile ? '32px 0' : '48px 0',
          borderTop: '1px solid rgba(255,255,255,0.05)',
        }}
      >
        <Container size="1200" px={sectionPx}>
          <Group justify="space-between" wrap="wrap" gap="md">
            <Group gap="sm">
              <Box
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  background: 'rgba(255,255,255,0.08)',
                  padding: 4,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <img src={logoMark} alt="Valore365" style={{ width: 20, height: 20, filter: 'brightness(2)' }} />
              </Box>
              <Text fw={700} c="rgba(255,255,255,0.7)" size="sm">
                Valore365
              </Text>
            </Group>
            <Text c="rgba(255,255,255,0.4)" size="xs">
              Il tuo portafoglio, sotto controllo. Sempre.
            </Text>
          </Group>
        </Container>
      </Box>
    </Box>
  );
}
