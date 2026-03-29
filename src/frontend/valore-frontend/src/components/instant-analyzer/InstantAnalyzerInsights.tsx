import { useState } from 'react';
import { Alert, Badge, Box, Button, Group, Loader, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconAlertTriangle, IconBulb, IconSparkles } from '@tabler/icons-react';
import { explainInstantInsight, type InstantAnalyzeResponse } from '../../services/api';

interface InstantAnalyzerInsightsProps {
  result: InstantAnalyzeResponse;
}

const SEVERITY_META = {
  high: { color: 'red', label: 'Alta priorita' },
  medium: { color: 'orange', label: 'Media priorita' },
} as const;

export function InstantAnalyzerInsights({ result }: InstantAnalyzerInsightsProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';
  const [activeInsightId, setActiveInsightId] = useState<string | null>(null);
  const [loadingInsightId, setLoadingInsightId] = useState<string | null>(null);
  const [explanations, setExplanations] = useState<Record<string, string>>({});
  const [explainError, setExplainError] = useState<string | null>(null);

  const cardStyle = {
    borderRadius: 16,
    border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
    background: isDark ? theme.colors.dark[6] : '#ffffff',
    padding: 24,
    boxShadow: isDark ? 'none' as const : '0 1px 3px rgba(0,0,0,0.04)',
  };

  const handleExplain = async (insightId: string) => {
    const insight = result.insights.find((item) => item.id === insightId);
    if (!insight) return;

    setActiveInsightId(insightId);
    setExplainError(null);

    if (explanations[insightId]) {
      return;
    }

    setLoadingInsightId(insightId);
    try {
      const response = await explainInstantInsight({ insight });
      setExplanations((current) => ({ ...current, [insightId]: response.explanation }));
    } catch (error) {
      setExplainError(error instanceof Error ? error.message : 'Impossibile ottenere la spiegazione in questo momento.');
    } finally {
      setLoadingInsightId(null);
    }
  };

  return (
    <Stack gap="md">
      <Box style={cardStyle}>
        <Group justify="space-between" mb="md" align="flex-start">
          <Group gap="sm">
            <ThemeIcon color="orange" variant="light" radius="xl">
              <IconAlertTriangle size={18} />
            </ThemeIcon>
            <div>
              <Title order={4} c={isDark ? 'white' : '#111827'}>Le 3 cose da capire adesso</Title>
              <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
                Insight ordinati per priorita e spiegabili in linguaggio semplice.
              </Text>
            </div>
          </Group>
          <Badge variant="light" color={result.insights.length > 0 ? 'orange' : 'teal'}>
            {result.insights.length}/3
          </Badge>
        </Group>

        <Stack gap="sm">
          {result.insights.length ? result.insights.map((insight, index) => {
            const severity = SEVERITY_META[insight.severity];
            const isActive = activeInsightId === insight.id;
            const explanation = explanations[insight.id];
            const isLoading = loadingInsightId === insight.id;

            return (
              <Box
                key={insight.id}
                style={{
                  padding: 18,
                  borderRadius: 14,
                  background: isDark ? theme.colors.dark[5] : '#f9fafb',
                  border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
                }}
              >
                <Stack gap="sm">
                  <Group justify="space-between" align="flex-start" wrap="wrap">
                    <Stack gap={4}>
                      <Group gap="xs">
                        <Badge variant="light" color={severity.color}>
                          {severity.label}
                        </Badge>
                        <Badge variant="dot" color="gray">
                          Insight {index + 1}
                        </Badge>
                      </Group>
                      <Text fw={700} c={isDark ? 'white' : '#111827'}>
                        {insight.title}
                      </Text>
                      <Text size="sm" c={isDark ? theme.colors.gray[4] : '#4b5563'}>
                        {insight.short_description}
                      </Text>
                    </Stack>

                    <Button
                      variant={isActive ? 'filled' : 'light'}
                      color={severity.color}
                      radius="md"
                      onClick={() => {
                        if (isActive && explanation) {
                          setActiveInsightId(null);
                          return;
                        }
                        void handleExplain(insight.id);
                      }}
                    >
                      {insight.cta_label}
                    </Button>
                  </Group>

                  {isActive && (
                    <Box
                      style={{
                        padding: 16,
                        borderRadius: 12,
                        background: isDark ? 'rgba(16, 185, 129, 0.08)' : '#ecfdf5',
                        border: isDark ? '1px solid rgba(16, 185, 129, 0.18)' : '1px solid #a7f3d0',
                      }}
                    >
                      {isLoading ? (
                        <Group gap="sm">
                          <Loader size="sm" color="teal" />
                          <Text size="sm" c={isDark ? theme.colors.gray[3] : '#065f46'}>
                            Sto preparando una spiegazione semplice di questo insight...
                          </Text>
                        </Group>
                      ) : explanation ? (
                        <Stack gap="xs">
                          <Group gap="xs">
                            <ThemeIcon color="teal" variant="light" radius="xl" size="sm">
                              <IconSparkles size={12} />
                            </ThemeIcon>
                            <Text fw={700} size="sm" c={isDark ? 'white' : '#065f46'}>
                              Spiegazione
                            </Text>
                          </Group>
                          <Text size="sm" c={isDark ? theme.colors.gray[2] : '#064e3b'}>
                            {explanation}
                          </Text>
                        </Stack>
                      ) : (
                        <Text size="sm" c={isDark ? theme.colors.gray[4] : '#6b7280'}>
                          Nessuna spiegazione disponibile.
                        </Text>
                      )}
                    </Box>
                  )}
                </Stack>
              </Box>
            );
          }) : (
            <Alert color="teal" variant="light" radius="md">
              Non emergono criticita forti nei tre insight principali. Il portafoglio appare relativamente bilanciato sui segnali coperti da questa analisi.
            </Alert>
          )}

          {explainError && (
            <Alert color="red" variant="light" radius="md">
              {explainError}
            </Alert>
          )}
        </Stack>
      </Box>

      {(result.alerts.length > 0 || result.suggestions.length > 0) && (
        <Box style={cardStyle}>
          <Group gap="sm" mb="md">
            <ThemeIcon color="teal" variant="light" radius="xl">
              <IconBulb size={18} />
            </ThemeIcon>
            <Title order={4} c={isDark ? 'white' : '#111827'}>Dettagli di supporto</Title>
          </Group>

          <Stack gap="sm">
            {result.alerts.slice(0, 2).map((alert) => (
              <Alert
                key={`${alert.code}-${alert.message}`}
                color={alert.severity === 'critical' ? 'red' : 'orange'}
                variant="light"
                radius="md"
              >
                {alert.message}
              </Alert>
            ))}
            {result.suggestions.slice(0, 2).map((suggestion) => (
              <Alert key={`${suggestion.code}-${suggestion.message}`} color="teal" variant="light" radius="md">
                {suggestion.message}
              </Alert>
            ))}
          </Stack>
        </Box>
      )}
    </Stack>
  );
}
