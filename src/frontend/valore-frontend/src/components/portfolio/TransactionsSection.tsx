import type { ReactNode } from 'react';
import { Card, Group, Loader, Select, Table, Text, TextInput, Title } from '@mantine/core';

interface TransactionsSectionProps {
  loading: boolean;
  filterQuery: string;
  onFilterQueryChange: (value: string) => void;
  filterSide: string;
  onFilterSideChange: (value: string) => void;
  rows: ReactNode;
  hasRows: boolean;
  selectedPortfolioId: string | null;
}

export function TransactionsSection({
  loading,
  filterQuery,
  onFilterQueryChange,
  filterSide,
  onFilterSideChange,
  rows,
  hasRows,
  selectedPortfolioId,
}: TransactionsSectionProps) {
  return (
    <Card withBorder mt="lg">
      <Group justify="space-between" mb="sm">
        <Title order={4}>Storico Transazioni</Title>
        {loading && (
          <Group gap="xs">
            <Loader size="xs" />
            <Text size="sm" c="dimmed">Caricamento...</Text>
          </Group>
        )}
      </Group>
      <Group mb="sm" grow>
        <TextInput
          label="Filtro testo"
          placeholder="Ticker, nome asset, note"
          value={filterQuery}
          onChange={(event) => onFilterQueryChange(event.currentTarget.value)}
        />
        <Select
          label="Tipo"
          data={[
            { value: 'all', label: 'Tutti' },
            { value: 'buy', label: 'BUY' },
            { value: 'sell', label: 'SELL' },
          ]}
          value={filterSide}
          onChange={(value) => onFilterSideChange(value ?? 'all')}
        />
      </Group>
      <Table.ScrollContainer minWidth={600}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Data</Table.Th>
              <Table.Th>Tipo</Table.Th>
              <Table.Th>Asset</Table.Th>
              <Table.Th style={{ textAlign: 'right' }} visibleFrom="sm">Qta</Table.Th>
              <Table.Th style={{ textAlign: 'right' }} visibleFrom="sm">Prezzo</Table.Th>
              <Table.Th style={{ textAlign: 'right' }} visibleFrom="md">Fee</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>Totale</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>Azioni</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {hasRows ? (
              rows
            ) : (
              <Table.Tr>
                <Table.Td colSpan={8}>
                  <Text c="dimmed" ta="center">
                    {selectedPortfolioId ? 'Nessuna transazione presente' : 'Seleziona un portafoglio'}
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}
