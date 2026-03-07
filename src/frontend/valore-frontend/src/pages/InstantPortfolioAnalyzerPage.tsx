import { useState } from 'react';
import { Alert, Box, Container, Grid, Group, Stack, Text, Title } from '@mantine/core';
import { IconShieldCheck, IconSparkles, IconTargetArrow } from '@tabler/icons-react';
import { InstantAnalyzerForm } from '../components/instant-analyzer/InstantAnalyzerForm';
import { InstantAnalyzerResults } from '../components/instant-analyzer/InstantAnalyzerResults';
import { analyzeInstantPortfolio, type InstantAnalyzeResponse } from '../services/api';

export function InstantPortfolioAnalyzerPage() {
  const [rawText, setRawText] = useState('VWCE 10000\nAGGH 5000\nEIMI 2000');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InstantAnalyzeResponse | null>(null);

  const handleSubmit = async () => {
    if (!rawText.trim()) {
      setError('Paste at least one position before running the analysis.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await analyzeInstantPortfolio({ input_mode: 'raw_text', raw_text: rawText });
      setResult(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to analyze this portfolio right now.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      style={{
        minHeight: '100vh',
        background: 'radial-gradient(circle at top left, rgba(255,204,102,0.35), transparent 28%), linear-gradient(180deg, #fff8eb 0%, #fff 22%, #f5fbff 100%)',
        padding: '48px 0 72px',
      }}
    >
      <Container size="xl">
        <Stack gap="xl">
          <Stack gap="md" maw={780}>
            <Group gap="sm">
              <Group gap={6}>
                <IconSparkles size={18} />
                <Text fw={700}>Public instant analysis</Text>
              </Group>
            </Group>
            <Title order={1} style={{ fontSize: 'clamp(2.5rem, 6vw, 4.5rem)', lineHeight: 1.02 }}>
              Check your portfolio health in 30 seconds
            </Title>
            <Text size="xl" c="dimmed" maw={720}>
              Paste your ETF and stock positions and get an instant health score, risk diagnosis, and diversification insights.
            </Text>
            <Group gap="xl" wrap="wrap">
              <Group gap="xs"><IconTargetArrow size={18} /><Text>Value-first onboarding</Text></Group>
              <Group gap="xs"><IconShieldCheck size={18} /><Text>No login required</Text></Group>
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
                }}
              />
            </Grid.Col>

            <Grid.Col span={{ base: 12, lg: 7 }}>
              {result ? (
                <InstantAnalyzerResults result={result} />
              ) : (
                <Alert color="blue" variant="light" radius="xl" title="What you will get">
                  Score, diversification snapshot, overlap warnings, cost signals, and a signup CTA once the analysis is ready.
                </Alert>
              )}
            </Grid.Col>
          </Grid>
        </Stack>
      </Container>
    </Box>
  );
}
