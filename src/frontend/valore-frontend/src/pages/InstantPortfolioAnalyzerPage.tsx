import { useState } from 'react';
import { Alert, Box, Container, Grid, Group, Stack, Text, Title } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconShieldCheck, IconSparkles, IconTargetArrow } from '@tabler/icons-react';
import logoMark from '../assets/logo-mark.svg';
import { InstantAnalyzerForm } from '../components/instant-analyzer/InstantAnalyzerForm';
import { InstantAnalyzerInputIssues } from '../components/instant-analyzer/InstantAnalyzerInputIssues';
import { InstantAnalyzerResults } from '../components/instant-analyzer/InstantAnalyzerResults';
import {
  ApiRequestError,
  analyzeInstantPortfolio,
  type InstantAnalyzeLineError,
  type InstantAnalyzeResponse,
  type InstantAnalyzeUnresolvedItem,
} from '../services/api';

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

export function InstantPortfolioAnalyzerPage() {
  const [rawText, setRawText] = useState('VWCE 10000\nAGGH 5000\nEIMI 2000');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InstantAnalyzeResponse | null>(null);
  const [errorDetails, setErrorDetails] = useState<InstantAnalyzerErrorDetails>({ parseErrors: [], unresolved: [] });

  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const isMobile = useMediaQuery('(max-width: 48em)');

  const handleSubmit = async () => {
    if (!rawText.trim()) {
      setError('Incolla almeno una posizione prima di avviare l\'analisi.');
      setErrorDetails({ parseErrors: [], unresolved: [] });
      return;
    }
    setLoading(true);
    setError(null);
    setErrorDetails({ parseErrors: [], unresolved: [] });
    try {
      const response = await analyzeInstantPortfolio({ input_mode: 'raw_text', raw_text: rawText });
      setResult(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Impossibile analizzare questo portafoglio in questo momento.');
      setResult(null);
      setErrorDetails(readErrorDetails(requestError));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      style={{
        minHeight: '100vh',
        background: isDark
          ? `radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 22%), radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 26%), linear-gradient(180deg, ${theme.colors.dark[8]} 0%, ${theme.colors.dark[7]} 100%)`
          : 'radial-gradient(circle at top left, rgba(37, 99, 235, 0.10), transparent 22%), radial-gradient(circle at top right, rgba(16, 185, 129, 0.10), transparent 26%), linear-gradient(180deg, #fbfeff 0%, #ffffff 24%, #f7fcfa 100%)',
        padding: isMobile ? '24px 0 48px' : '48px 0 72px',
      }}
    >
      <Container fluid px={isMobile ? 'md' : 'xl'}>
        <Stack gap="xl">
          <Stack gap="md" maw={860}>
            <Group gap={isMobile ? 'md' : 'lg'} align="center" wrap="nowrap">
              <Box
                style={{
                  width: isMobile ? 56 : 88,
                  height: isMobile ? 56 : 88,
                  minWidth: isMobile ? 56 : 88,
                  borderRadius: isMobile ? 18 : 26,
                  background: isDark
                    ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[5]} 100%)`
                    : 'linear-gradient(180deg, #ffffff 0%, #f2fbf8 100%)',
                  border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid rgba(37, 99, 235, 0.12)',
                  boxShadow: isDark ? '0 22px 44px rgba(0, 0, 0, 0.2)' : '0 22px 44px rgba(15, 23, 42, 0.12)',
                  padding: isMobile ? 8 : 12,
                }}
              >
                <img
                  src={logoMark}
                  alt="Logo Valore365"
                  style={{ width: '100%', height: '100%', display: 'block' }}
                />
              </Box>
              <Stack gap={2}>
                <Title order={2} c={isDark ? 'white' : '#0f172a'} style={{ fontSize: isMobile ? '1.6rem' : 'clamp(2.1rem, 5vw, 3.4rem)', lineHeight: 1 }}>
                  Valore365
                </Title>
                <Text c={isDark ? theme.colors.blue[3] : '#2563eb'} fw={700} size={isMobile ? 'md' : 'lg'}>
                  Instant Analyzer
                </Text>
              </Stack>
            </Group>

            <Group gap="sm">
              <Group
                gap={6}
                style={{
                  background: isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(255, 255, 255, 0.78)',
                  border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid rgba(37, 99, 235, 0.1)',
                  borderRadius: 999,
                  padding: '8px 14px',
                  boxShadow: isDark ? '0 10px 24px rgba(0, 0, 0, 0.2)' : '0 10px 24px rgba(15, 23, 42, 0.08)',
                }}
              >
                <IconSparkles size={18} color={isDark ? theme.colors.blue[3] : '#2563eb'} />
                <Text fw={700} c={isDark ? theme.colors.gray[2] : '#1e293b'} size={isMobile ? 'sm' : undefined}>
                  Analisi istantanea pubblica
                </Text>
              </Group>
            </Group>
            <Title
              order={1}
              c={isDark ? 'white' : '#0f172a'}
              style={{
                fontSize: isMobile ? '1.8rem' : 'clamp(2.5rem, 6vw, 4.5rem)',
                lineHeight: 1.02,
                letterSpacing: '-0.04em',
              }}
            >
              Controlla la salute del tuo portafoglio in 30 secondi
            </Title>
            <Text
              size={isMobile ? 'md' : 'xl'}
              c={isDark ? theme.colors.gray[4] : '#334155'}
              maw={720}
              style={{ lineHeight: 1.5 }}
            >
              Incolla le tue posizioni in ETF e azioni e ottieni subito uno score, una diagnosi del rischio e indicazioni sulla diversificazione.
            </Text>
            <Group gap="xl" wrap="wrap" c={isDark ? theme.colors.gray[3] : '#1e293b'}>
              <Group gap="xs"><IconTargetArrow size={18} color={isDark ? theme.colors.blue[4] : '#1d4ed8'} /><Text fw={600} size={isMobile ? 'sm' : undefined}>Valore prima del signup</Text></Group>
              <Group gap="xs"><IconShieldCheck size={18} color={isDark ? theme.colors.teal[4] : '#0f766e'} /><Text fw={600} size={isMobile ? 'sm' : undefined}>Nessun login richiesto</Text></Group>
            </Group>
          </Stack>

          <Grid gutter="xl" align="start">
            <Grid.Col span={{ base: 12, lg: 5 }}>
              <InstantAnalyzerForm
                value={rawText}
                error={error}
                loading={loading}
                onChange={setRawText}
                onSubmit={handleSubmit}
                onReset={() => {
                  setRawText('');
                  setResult(null);
                  setError(null);
                  setErrorDetails({ parseErrors: [], unresolved: [] });
                }}
              />
            </Grid.Col>

            <Grid.Col span={{ base: 12, lg: 7 }}>
              {result ? (
                <InstantAnalyzerResults result={result} />
              ) : (
                <Stack gap="lg">
                  <Alert color="blue" variant="light" radius="xl" title="Cosa otterrai">
                    Score complessivo, quadro della diversificazione, breakdown dello score, avvisi su sovrapposizioni e costi, oltre alla CTA finale per creare un account.
                  </Alert>
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
  );
}
