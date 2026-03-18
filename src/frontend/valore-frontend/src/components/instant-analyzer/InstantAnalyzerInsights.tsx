import { Alert, Badge, Box, Group, Stack, Text, ThemeIcon, Title } from '@mantine/core';
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

  const cardStyle = {
    borderRadius: 16,
    border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
    background: isDark ? theme.colors.dark[6] : '#ffffff',
    padding: 24,
    boxShadow: isDark ? 'none' as const : '0 1px 3px rgba(0,0,0,0.04)',
  };

  return (
    <Stack gap="md">
      <Box style={cardStyle}>
        <Group justify="space-between" mb="md">
          <Group gap="sm">
            <ThemeIcon color="orange" variant="light" radius="xl">
              <IconAlertTriangle size={18} />
            </ThemeIcon>
            <Title order={4} c={isDark ? 'white' : '#111827'}>Avvisi</Title>
          </Group>
          <Badge variant="light" color={result.alerts.length > 0 ? 'orange' : 'gray'}>{result.alerts.length}</Badge>
        </Group>
        <Stack gap="sm">
          {result.alerts.length ? result.alerts.map((alert) => (
            <Alert key={`${alert.code}-${alert.message}`} color={alert.severity === 'critical' ? 'red' : 'orange'} variant="light" radius="md">
              {alert.message}
            </Alert>
          )) : <Text c="dimmed" size="sm">Nessun avviso rilevante in questa analisi.</Text>}
        </Stack>
      </Box>

      <Box style={cardStyle}>
        <Group justify="space-between" mb="md">
          <Group gap="sm">
            <ThemeIcon color="teal" variant="light" radius="xl">
              <IconBulb size={18} />
            </ThemeIcon>
            <Title order={4} c={isDark ? 'white' : '#111827'}>Suggerimenti</Title>
          </Group>
          <Badge variant="light" color={result.suggestions.length > 0 ? 'teal' : 'gray'}>{result.suggestions.length}</Badge>
        </Group>
        <Stack gap="sm">
          {result.suggestions.length ? result.suggestions.map((suggestion) => (
            <Alert key={`${suggestion.code}-${suggestion.message}`} color="teal" variant="light" radius="md">
              {suggestion.message}
            </Alert>
          )) : <Text c="dimmed" size="sm">Nessuna modifica immediata suggerita.</Text>}
        </Stack>
      </Box>
    </Stack>
  );
}
