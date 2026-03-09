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
    <Card
      radius="xl"
      padding="xl"
      withBorder
      style={{
        background: 'linear-gradient(145deg, #fff7df 0%, #fffef9 58%, #eef6fb 100%)',
        borderColor: 'rgba(15, 23, 42, 0.1)',
        boxShadow: '0 18px 40px rgba(15, 23, 42, 0.08)',
      }}
    >
      <Stack gap="lg">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text tt="uppercase" fw={800} size="xs" c="#7c2d12">
              Portfolio Health
            </Text>
            <Title order={2} c="#0f172a">{result.summary.score} / 100</Title>
            <Text c="#475569">Valore analizzato: EUR {result.summary.total_value.toLocaleString('it-IT')}</Text>
          </div>
          <Badge color={tone.color} size="lg" radius="sm">
            {tone.label}
          </Badge>
        </Group>

        <Progress value={result.summary.score} color={tone.color} radius="xl" size="lg" />

        <SimpleGrid cols={{ base: 2, md: 4 }} spacing="md">
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="#64748b">Risk</Text>
            <Text fw={700} c="#0f172a">{result.summary.risk_level}</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="#64748b">Diversification</Text>
            <Text fw={700} c="#0f172a">{result.summary.diversification}</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="#64748b">Overlap</Text>
            <Text fw={700} c="#0f172a">{result.summary.overlap}</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="#64748b">Costs</Text>
            <Text fw={700} c="#0f172a">{result.summary.cost_efficiency}</Text>
          </Stack>
        </SimpleGrid>

        <SimpleGrid cols={{ base: 2, md: 5 }} spacing="md">
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="#64748b">Diversification</Text>
            <Text fw={700} c="#0f172a">{result.category_scores.diversification} / 25</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="#64748b">Risk score</Text>
            <Text fw={700} c="#0f172a">{result.category_scores.risk} / 25</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="#64748b">Concentration</Text>
            <Text fw={700} c="#0f172a">{result.category_scores.concentration} / 20</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="#64748b">Overlap score</Text>
            <Text fw={700} c="#0f172a">{result.category_scores.overlap} / 15</Text>
          </Stack>
          <Stack gap={2}>
            <Text size="xs" tt="uppercase" c="#64748b">Cost score</Text>
            <Text fw={700} c="#0f172a">{result.category_scores.cost_efficiency} / 15</Text>
          </Stack>
        </SimpleGrid>
      </Stack>
    </Card>
  );
}
