import { Alert, Badge, Card, Group, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconAlertTriangle, IconBulb } from '@tabler/icons-react';
import type { InstantAnalyzeResponse } from '../../services/api';

interface InstantAnalyzerInsightsProps {
  result: InstantAnalyzeResponse;
}

export function InstantAnalyzerInsights({ result }: InstantAnalyzerInsightsProps) {
  return (
    <Stack gap="md">
      <Card withBorder radius="xl" padding="lg" style={{ borderColor: 'rgba(15, 23, 42, 0.1)', background: '#fffdf9' }}>
        <Group justify="space-between" mb="md">
          <Group gap="sm">
            <ThemeIcon color="orange" variant="light" radius="xl">
              <IconAlertTriangle size={18} />
            </ThemeIcon>
            <Title order={4}>Avvisi</Title>
          </Group>
          <Badge variant="light">{result.alerts.length}</Badge>
        </Group>
        <Stack gap="sm">
          {result.alerts.length ? result.alerts.map((alert) => (
            <Alert key={`${alert.code}-${alert.message}`} color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light">
              {alert.message}
            </Alert>
          )) : <Text c="#475569">Nessun avviso rilevante in questa analisi.</Text>}
        </Stack>
      </Card>

      <Card withBorder radius="xl" padding="lg" style={{ borderColor: 'rgba(15, 23, 42, 0.1)', background: '#f8fcfb' }}>
        <Group justify="space-between" mb="md">
          <Group gap="sm">
            <ThemeIcon color="teal" variant="light" radius="xl">
              <IconBulb size={18} />
            </ThemeIcon>
            <Title order={4}>Suggerimenti</Title>
          </Group>
          <Badge variant="light">{result.suggestions.length}</Badge>
        </Group>
        <Stack gap="sm">
          {result.suggestions.length ? result.suggestions.map((suggestion) => (
            <Alert key={`${suggestion.code}-${suggestion.message}`} color="teal" variant="light">
              {suggestion.message}
            </Alert>
          )) : <Text c="#475569">Nessuna modifica immediata suggerita.</Text>}
        </Stack>
      </Card>
    </Stack>
  );
}
