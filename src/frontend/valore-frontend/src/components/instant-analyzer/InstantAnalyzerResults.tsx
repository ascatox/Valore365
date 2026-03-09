import { Alert, Badge, Button, Card, Group, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core';
import { IconArrowRight, IconChartDonut3 } from '@tabler/icons-react';
import type { InstantAnalyzeResponse } from '../../services/api';
import { InstantAnalyzerInputIssues } from './InstantAnalyzerInputIssues';
import { InstantAnalyzerInsights } from './InstantAnalyzerInsights';
import { InstantAnalyzerScoreCard } from './InstantAnalyzerScoreCard';

interface InstantAnalyzerResultsProps {
  result: InstantAnalyzeResponse;
}

const clerkEnabled = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function formatPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'N/D';
  return `${value.toFixed(1)}%`;
}

export function InstantAnalyzerResults({ result }: InstantAnalyzerResultsProps) {
  return (
    <Stack gap="lg">
      <InstantAnalyzerScoreCard result={result} />

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <Card withBorder radius="xl" padding="lg" style={{ borderColor: 'rgba(15, 23, 42, 0.1)', background: '#fffefb' }}>
          <Group gap="sm" mb="md">
            <IconChartDonut3 size={18} />
            <Title order={4}>Metriche chiave</Title>
          </Group>
          <Table withTableBorder withColumnBorders highlightOnHover>
            <Table.Tbody>
              <Table.Tr><Table.Td>Esposizione USA</Table.Td><Table.Td>{formatPct(result.metrics.geographic_exposure.usa)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Esposizione Europa</Table.Td><Table.Td>{formatPct(result.metrics.geographic_exposure.europe)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Esposizione Emergenti</Table.Td><Table.Td>{formatPct(result.metrics.geographic_exposure.emerging)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Posizione massima</Table.Td><Table.Td>{formatPct(result.metrics.max_position_weight)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Score overlap</Table.Td><Table.Td>{formatPct(result.metrics.overlap_score)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Volatilità</Table.Td><Table.Td>{formatPct(result.metrics.portfolio_volatility)}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td>Weighted TER</Table.Td><Table.Td>{formatPct(result.metrics.weighted_ter)}</Table.Td></Table.Tr>
            </Table.Tbody>
          </Table>
        </Card>

        <Card withBorder radius="xl" padding="lg" style={{ borderColor: 'rgba(15, 23, 42, 0.1)', background: '#f9fcff' }}>
          <Title order={4} mb="md" c="#0f172a">Posizioni risolte</Title>
          <Stack gap="sm">
            {result.positions.map((position) => (
              <Group key={`${position.identifier}-${position.resolved_symbol}`} justify="space-between" align="flex-start">
                <div>
                  <Text fw={700} c="#0f172a">{position.resolved_symbol}</Text>
                  <Text size="sm" c="#475569">{position.resolved_name}</Text>
                </div>
                <Stack gap={2} align="flex-end">
                  <Badge variant="light">{position.weight.toFixed(2)}%</Badge>
                  <Text size="sm" c="#1e293b">EUR {position.value.toLocaleString('it-IT')}</Text>
                </Stack>
              </Group>
            ))}
          </Stack>
        </Card>
      </SimpleGrid>

      <InstantAnalyzerInsights result={result} />

      <InstantAnalyzerInputIssues
        parseErrors={result.parse_errors}
        unresolved={result.unresolved}
      />

      {result.cta.show_signup && (
        <Card radius="xl" padding="xl" withBorder style={{ background: 'linear-gradient(135deg, #183153 0%, #245f73 100%)', color: 'white' }}>
          <Group justify="space-between" align="center">
            <div>
              <Text tt="uppercase" fw={800} size="xs" style={{ opacity: 0.7 }}>Prossimo passo</Text>
              <Title order={3} c="white" mt={4}>{result.cta.message}</Title>
            </div>
            <Button
              component="a"
              href={clerkEnabled ? '/sign-up' : '/portfolio'}
              rightSection={<IconArrowRight size={16} />}
              color="yellow"
              variant="filled"
              radius="xl"
            >
              Crea account gratis
            </Button>
          </Group>
        </Card>
      )}
    </Stack>
  );
}
