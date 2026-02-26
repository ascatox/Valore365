import type { ReactNode } from 'react';
import { Button, Card, Group, SimpleGrid, Table, Text, Title } from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';

interface TargetAllocationSectionProps {
  allocationsCount: number;
  totalWeight: number;
  portfolioTargetNotionalLabel: string;
  assignedTargetValueLabel: string | null;
  selectedPortfolioId: string | null;
  rows: ReactNode;
  hasRows: boolean;
  onOpenAddAssetWeight: () => void;
  showActions?: boolean;
}

export function TargetAllocationSection({
  allocationsCount,
  totalWeight,
  portfolioTargetNotionalLabel,
  assignedTargetValueLabel,
  selectedPortfolioId,
  rows,
  hasRows,
  onOpenAddAssetWeight,
  showActions = true,
}: TargetAllocationSectionProps) {
  return (
    <>
      <SimpleGrid cols={{ base: 1, md: 4 }} mb="lg">
        <Card withBorder>
          <Text size="sm" c="dimmed">Asset in target</Text>
          <Text fw={700} size="xl">{allocationsCount}</Text>
        </Card>
        <Card withBorder>
          <Text size="sm" c="dimmed">Peso totale assegnato</Text>
          <Text fw={700} size="xl">{totalWeight.toFixed(2)}%</Text>
        </Card>
        <Card withBorder>
          <Text size="sm" c="dimmed">Peso residuo</Text>
          <Text fw={700} size="xl" c={totalWeight > 100 ? 'red' : 'teal'}>
            {(100 - totalWeight).toFixed(2)}%
          </Text>
        </Card>
        <Card withBorder>
          <Text size="sm" c="dimmed">Controvalore target</Text>
          <Text fw={700} size="xl">{portfolioTargetNotionalLabel}</Text>
          {assignedTargetValueLabel && (
            <Text size="xs" c="dimmed" mt="xs">
              Assegnato: {assignedTargetValueLabel}
            </Text>
          )}
        </Card>
      </SimpleGrid>

      <Card withBorder mb="lg">
        <Group justify="space-between" mb="sm" wrap="wrap" gap="xs">
          <Title order={4}>Allocazione target</Title>
          {showActions && (
            <Button leftSection={<IconPlus size={16} />} variant="light" onClick={onOpenAddAssetWeight} disabled={!selectedPortfolioId}>
              Aggiungi Asset / Peso
            </Button>
          )}
        </Group>
        <Table.ScrollContainer minWidth={450}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Asset</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Peso Target</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>Controvalore Target</Table.Th>
                {showActions && <Table.Th style={{ textAlign: 'right' }}>Azioni</Table.Th>}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {hasRows ? (
                rows
              ) : (
                <Table.Tr>
                  <Table.Td colSpan={showActions ? 4 : 3}>
                    <Text c="dimmed" ta="center">
                      {selectedPortfolioId ? 'Nessun asset assegnato al portafoglio' : 'Nessun portafoglio disponibile'}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
    </>
  );
}
