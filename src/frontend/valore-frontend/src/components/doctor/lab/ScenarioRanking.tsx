import { Badge, Box, Card, Group, Stack, Table, Text } from '@mantine/core';
import type { DoctorScenarioRankItem } from '../../../services/api/types';
import { formatMoney, formatPctValue, NOT_AVAILABLE } from '../policy/policyFormat';

export const RANKING_CRITERIA = 'Ordinamento secondo i criteri: conformità, costi, turnover';
const RANKING_NOTE = 'È un ordinamento, non una raccomandazione: con preferenze diverse non esiste una scelta valida per tutti.';
const FIRST_LABEL = 'Primo secondo questi criteri';

interface ScenarioRankingProps {
  ranking: DoctorScenarioRankItem[];
  bestIndex: number | null;
  /** Scenario names by index (fallback when the ranking has no label). */
  names: string[];
  currency: string;
  privacy: boolean;
  isMobile: boolean;
}

const count = (value: number | null | undefined) => (value == null ? NOT_AVAILABLE : String(value));

/** Ranking of the compared scenarios exactly as the backend orders them (neutral wording, no advice). */
export function ScenarioRanking({ ranking, bestIndex, names, currency, privacy, isMobile }: ScenarioRankingProps) {
  if (!ranking.length) return null;
  const rows = [...ranking].sort((left, right) => left.rank - right.rank);
  const nameOf = (item: DoctorScenarioRankItem) => item.label || names[item.index] || `Scenario ${String.fromCharCode(65 + item.index)}`;
  const isFirst = (item: DoctorScenarioRankItem) => bestIndex != null && item.index === bestIndex;
  const firstBadge = <Badge size="xs" variant="light" color="gray">{FIRST_LABEL}</Badge>;

  return (
    <Box data-testid="scenario-ranking">
      <Text size="sm" fw={700}>{RANKING_CRITERIA}</Text>
      <Text size="xs" c="dimmed" mb={6}>{RANKING_NOTE}</Text>
      {isMobile ? (
        <Stack gap="xs">
          {rows.map((item) => (
            <Card key={item.index} withBorder radius="md" padding="sm">
              <Group gap={6} wrap="wrap">
                <Text size="sm" fw={700}>{`${item.rank}. ${nameOf(item)}`}</Text>
                {isFirst(item) && firstBadge}
              </Group>
              <Text size="xs">{`${item.feasible ? 'Fattibile' : 'Non fattibile'} · violate dopo: ${count(item.failed_after)} · non verificabili dopo: ${count(item.unknown_after)}`}</Text>
              <Text size="xs">{`Costi: ${formatMoney(item.costs, currency, privacy)} · Turnover: ${formatPctValue(item.turnover_pct)}`}</Text>
            </Card>
          ))}
        </Stack>
      ) : (
        <Table.ScrollContainer minWidth={560}>
          <Table withTableBorder fz="sm">
            <Table.Caption>{RANKING_CRITERIA}</Table.Caption>
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">Posizione</Table.Th>
                <Table.Th scope="col">Scenario</Table.Th>
                <Table.Th scope="col">Fattibile</Table.Th>
                <Table.Th scope="col" ta="right">Violate dopo</Table.Th>
                <Table.Th scope="col" ta="right">Non verificabili dopo</Table.Th>
                <Table.Th scope="col" ta="right">Costi</Table.Th>
                <Table.Th scope="col" ta="right">Turnover</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((item) => (
                <Table.Tr key={item.index} data-testid={`ranking-row-${item.index}`}>
                  <Table.Td>{item.rank}</Table.Td>
                  <Table.Th scope="row">
                    <Group gap={6} wrap="wrap">
                      <Text size="sm" fw={500}>{nameOf(item)}</Text>
                      {isFirst(item) && firstBadge}
                    </Group>
                  </Table.Th>
                  <Table.Td>{item.feasible ? 'Sì' : 'No'}</Table.Td>
                  <Table.Td ta="right">{count(item.failed_after)}</Table.Td>
                  <Table.Td ta="right">{count(item.unknown_after)}</Table.Td>
                  <Table.Td ta="right">{formatMoney(item.costs, currency, privacy)}</Table.Td>
                  <Table.Td ta="right">{formatPctValue(item.turnover_pct)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Box>
  );
}
