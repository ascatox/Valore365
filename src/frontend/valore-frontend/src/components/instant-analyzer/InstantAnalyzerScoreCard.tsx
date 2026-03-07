import { Badge, Card, Group, Progress, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import type { InstantAnalyzeResponse } from '../../services/api';

interface InstantAnalyzerScoreCardProps {
  result: InstantAnalyzeResponse;
}

function summaryTone(score: number): { label: string; color: string } {
  if (score >= 80) return { label: 'Excellent', color: 'teal' };
  if (score >= 70) return { label: 'Good', color: 'blue' };
  if (score >= 60) return { label: 'Average', color: 'yellow' };
  return { label: 'Weak', color: 'red' };
}

export function InstantAnalyzerScoreCard({ result }: InstantAnalyzerScoreCardProps) {
  const tone = summaryTone(result.summary.score);

  return (
    <Card radius="xl" padding="xl" withBorder style={{ background: 'linear-gradient(145deg, #fff8e8 0%, #ffffff 55%, #f5fbff 100%)' }}>
      <Stack gap="lg">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text tt="uppercase" fw={800} size="xs" c="dimmed">
              Portfolio Health
            </Text>
            <Title order={2}>{result.summary.score} / 100</Title>
            <Text c="dimmed">Valore analizzato: EUR {result.summary.total_value.toLocaleString('it-IT')}</Text>
          </div>
          <Badge color={tone.color} size="lg" radius="sm">
            {tone.label}
          </Badge>
        </Group>

        <Progress value={result.summary.score} color={tone.color} radius="xl" size="lg" />

        <SimpleGrid cols={{ base: 2, md: 4 }} spacing="md">
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="dimmed">Risk</Text>
            <Text fw={700}>{result.summary.risk_level}</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="dimmed">Diversification</Text>
            <Text fw={700}>{result.summary.diversification}</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="dimmed">Overlap</Text>
            <Text fw={700}>{result.summary.overlap}</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="dimmed">Costs</Text>
            <Text fw={700}>{result.summary.cost_efficiency}</Text>
          </Stack>
        </SimpleGrid>
      </Stack>
    </Card>
  );
}
