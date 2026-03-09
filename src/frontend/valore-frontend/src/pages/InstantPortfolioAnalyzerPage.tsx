import { useState } from 'react';
import { Alert, Box, Container, Grid, Group, Stack, Text, Title } from '@mantine/core';
import { IconShieldCheck, IconSparkles, IconTargetArrow } from '@tabler/icons-react';
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

  const handleSubmit = async () => {
    if (!rawText.trim()) {
      setError('Paste at least one position before running the analysis.');
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
      setError(requestError instanceof Error ? requestError.message : 'Unable to analyze this portfolio right now.');
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
        background: 'radial-gradient(circle at top left, rgba(245, 158, 11, 0.22), transparent 24%), linear-gradient(180deg, #f6efe2 0%, #f4f1ea 18%, #edf4f8 100%)',
        padding: '48px 0 72px',
        color: '#0f172a',
      }}
    >
      <Container size="xl">
        <Stack gap="xl">
          <Stack gap="md" maw={780}>
            <Group gap="sm">
              <Group
                gap={6}
                style={{
                  background: 'rgba(255, 255, 255, 0.72)',
                  border: '1px solid rgba(15, 23, 42, 0.08)',
                  borderRadius: 999,
                  padding: '8px 14px',
                  boxShadow: '0 10px 24px rgba(15, 23, 42, 0.06)',
                }}
              >
                <IconSparkles size={18} color="#b45309" />
                <Text fw={700} c="#1e293b">Public instant analysis</Text>
              </Group>
            </Group>
            <Title order={1} c="#0f172a" style={{ fontSize: 'clamp(2.5rem, 6vw, 4.5rem)', lineHeight: 1.02, letterSpacing: '-0.04em' }}>
              Check your portfolio health in 30 seconds
            </Title>
            <Text size="xl" c="#334155" maw={720} style={{ lineHeight: 1.5 }}>
              Paste your ETF and stock positions and get an instant health score, risk diagnosis, and diversification insights.
            </Text>
            <Group gap="xl" wrap="wrap" style={{ color: '#1e293b' }}>
              <Group gap="xs"><IconTargetArrow size={18} color="#1d4ed8" /><Text fw={600}>Value-first onboarding</Text></Group>
              <Group gap="xs"><IconShieldCheck size={18} color="#0f766e" /><Text fw={600}>No login required</Text></Group>
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
                  <Alert color="blue" variant="light" radius="xl" title="What you will get">
                    Score, diversification snapshot, score breakdown, overlap warnings, cost signals, and a signup CTA once the analysis is ready.
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
