import { Alert, Box, Stack, Title } from '@mantine/core';
import { useComputedColorScheme, useMantineTheme } from '@mantine/core';
import type { InstantAnalyzeLineError, InstantAnalyzeUnresolvedItem } from '../../services/api';

interface InstantAnalyzerInputIssuesProps {
  parseErrors: InstantAnalyzeLineError[];
  unresolved: InstantAnalyzeUnresolvedItem[];
}

export function InstantAnalyzerInputIssues({
  parseErrors,
  unresolved,
}: InstantAnalyzerInputIssuesProps) {
  const theme = useMantineTheme();
  const colorScheme = useComputedColorScheme('light');
  const isDark = colorScheme === 'dark';

  if (!parseErrors.length && !unresolved.length) {
    return null;
  }

  return (
    <Box
      style={{
        borderRadius: 16,
        border: isDark ? `1px solid ${theme.colors.dark[4]}` : '1px solid #e5e7eb',
        background: isDark ? theme.colors.dark[6] : '#ffffff',
        padding: 24,
        boxShadow: isDark ? 'none' : '0 1px 3px rgba(0,0,0,0.04)',
      }}
    >
      <Title order={4} mb="md" c={isDark ? 'white' : '#111827'}>Problemi di input</Title>
      <Stack gap="sm">
        {parseErrors.map((error) => (
          <Alert key={`parse-${error.line}-${error.raw}`} color="red" variant="light" radius="md">
            Riga {error.line}: {error.error}
          </Alert>
        ))}
        {unresolved.map((item) => (
          <Alert key={`unresolved-${item.identifier}-${item.line ?? 'na'}`} color="yellow" variant="light" radius="md">
            {item.identifier}: {item.error}
          </Alert>
        ))}
      </Stack>
    </Box>
  );
}
