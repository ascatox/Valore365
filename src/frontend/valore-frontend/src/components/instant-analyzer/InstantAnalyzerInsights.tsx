import { Alert, Badge, Card, Group, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import { IconAlertTriangle, IconBulb } from '@tabler/icons-react';
import type { InstantAnalyzeResponse } from '../../services/api';

interface InstantAnalyzerInsightsProps {
  result: InstantAnalyzeResponse;
}

export function InstantAnalyzerInsights({ result }: InstantAnalyzerInsightsProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  const cardBg = isDark
    ? `linear-gradient(180deg, ${theme.colors.dark[6]} 0%, ${theme.colors.dark[7]} 100%)`
    : undefined;
  const cardBorder = isDark ? theme.colors.dark[4] : 'rgba(15, 23, 42, 0.1)';

  return (
    <Stack gap="md">
      <Card withBorder radius="xl" padding="lg" style={{ borderColor: cardBorder, background: cardBg ?? '#fffdf9' }}>
        <Group justify="space-between" mb="md">
          <Group gap="sm">
            <ThemeIcon color="orange" variant="light" radius="xl">
              <IconAlertTriangle size={18} />
            </ThemeIcon>
            <Title order={4} c={isDark ? 'white' : undefined}>Avvisi</Title>
          </Group>
          <Badge variant="light" color={result.alerts.length > 0 ? 'orange' : 'gray'}>{result.alerts.length}</Badge>
        </Group>
        <Stack gap="sm">
          {result.alerts.length ? result.alerts.map((alert) => (
            <Alert key={`${alert.code}-${alert.message}`} color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light">
              {alert.message}
            </Alert>
          )) : <Text c="dimmed">Nessun avviso rilevante in questa analisi.</Text>}
        </Stack>
      </Card>

      <Card withBorder radius="xl" padding="lg" style={{ borderColor: cardBorder, background: cardBg ?? '#f8fcfb' }}>
        <Group justify="space-between" mb="md">
          <Group gap="sm">
            <ThemeIcon color="teal" variant="light" radius="xl">
              <IconBulb size={18} />
            </ThemeIcon>
            <Title order={4} c={isDark ? 'white' : undefined}>Suggerimenti</Title>
          </Group>
          <Badge variant="light" color={result.suggestions.length > 0 ? 'teal' : 'gray'}>{result.suggestions.length}</Badge>
        </Group>
        <Stack gap="sm">
          {result.suggestions.length ? result.suggestions.map((suggestion) => (
            <Alert key={`${suggestion.code}-${suggestion.message}`} color="teal" variant="light">
              {suggestion.message}
            </Alert>
          )) : <Text c="dimmed">Nessuna modifica immediata suggerita.</Text>}
        </Stack>
      </Card>
    </Stack>
  );
}
