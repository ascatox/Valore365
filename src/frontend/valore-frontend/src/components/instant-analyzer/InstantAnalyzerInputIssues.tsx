import { Alert, Card, Stack, Title } from '@mantine/core';
import type { InstantAnalyzeLineError, InstantAnalyzeUnresolvedItem } from '../../services/api';

interface InstantAnalyzerInputIssuesProps {
  parseErrors: InstantAnalyzeLineError[];
  unresolved: InstantAnalyzeUnresolvedItem[];
}

export function InstantAnalyzerInputIssues({
  parseErrors,
  unresolved,
}: InstantAnalyzerInputIssuesProps) {
  if (!parseErrors.length && !unresolved.length) {
    return null;
  }

  return (
    <Card withBorder radius="xl" padding="lg" style={{ borderColor: 'rgba(15, 23, 42, 0.1)', background: '#fffdf8' }}>
      <Title order={4} mb="md" c="#0f172a">Problemi di input</Title>
      <Stack gap="sm">
        {parseErrors.map((error) => (
          <Alert key={`parse-${error.line}-${error.raw}`} color="red" variant="light">
            Riga {error.line}: {error.error}
          </Alert>
        ))}
        {unresolved.map((item) => (
          <Alert key={`unresolved-${item.identifier}-${item.line ?? 'na'}`} color="yellow" variant="light">
            {item.identifier}: {item.error}
          </Alert>
        ))}
      </Stack>
    </Card>
  );
}
